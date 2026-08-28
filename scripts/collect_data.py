#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日财经日报数据采集脚本（增强版）

采集五大类数据，输出结构化 JSON：
1. 国家统计局 - 最新发布 + 发布预告
2. A股行情 - 5大主要指数（腾讯财经API）
3. 行业板块 - 涨跌幅排行（新浪财经API）
4. 全球市场 - 美股/黄金/汇率（东方财富API）
5. 财经新闻 - 50条新闻+分类+Top5摘要（新浪财经）

特性：
- 多源降级，自动切换备用数据源
- 3次重试，指数退避
- 历史数据缓存，支持环比对比
- 完整执行日志
- 结构化JSON输出

使用方式：
    python3 collect_data.py [--output output.json] [--date YYYY-MM-DD] [--no-cache]
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import argparse
import os
import sys
import re
import random
from datetime import datetime, timedelta
from urllib.parse import urljoin

# 导入重试工具
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import retry, retry_request, logger as utils_logger

# ============================================
# 配置
# ============================================
DEFAULT_TIMEOUT = (10, 25)
MAX_RETRIES = 4
RETRY_DELAY = 2

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(BASE_HEADERS)

HEADERS = BASE_HEADERS.copy()
HEADERS["User-Agent"] = USER_AGENTS[0]

def get_random_headers(referer=None):
    headers = BASE_HEADERS.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)
    if referer:
        headers["Referer"] = referer
    return headers

def random_delay(min_sec=0.3, max_sec=0.8):
    time.sleep(random.uniform(min_sec, max_sec))

STATS_URL = "https://www.stats.gov.cn/"
SINA_URL = "https://finance.sina.com.cn/"
# 使用基于脚本位置的绝对路径，避免从其他目录运行时路径错误
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CACHE_DIR = os.path.join(PROJECT_DIR, "cache")
LOG_DIR = os.path.join(PROJECT_DIR, "logs")

ERRORS = []
LOGS = []


# ============================================
# 工具函数
# ============================================
def log(level, message):
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line, flush=True)
    LOGS.append(log_line)
    if level == "ERROR":
        ERRORS.append(message)


def log_info(msg): log("INFO", msg)
def log_warn(msg): log("WARN", msg)
def log_error(msg): log("ERROR", msg)


def fetch_with_retry(url, headers=None, timeout=DEFAULT_TIMEOUT, retries=MAX_RETRIES, encoding=None, use_session=True):
    """带重试的 HTTP GET 请求（使用Session复用连接 + 随机UA）"""
    merged_headers = get_random_headers()
    if headers:
        merged_headers.update(headers)
    for attempt in range(retries):
        try:
            if use_session:
                response = SESSION.get(url, headers=merged_headers, timeout=timeout, allow_redirects=True)
            else:
                response = requests.get(url, headers=merged_headers, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            if encoding:
                response.encoding = encoding
            else:
                if response.encoding == 'ISO-8859-1':
                    response.encoding = response.apparent_encoding or 'utf-8'
            return response
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                log_warn(f"请求超时 ({url[:60]}...)，{delay}秒后重试 ({attempt+1}/{retries})")
                time.sleep(delay)
            else:
                log_error(f"请求超时，已重试{retries}次: {url[:80]}")
                return None
        except requests.exceptions.HTTPError as e:
            if attempt < retries - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                log_warn(f"HTTP错误 {e.response.status_code} ({url[:60]}...)，{delay}秒后重试")
                time.sleep(delay)
            else:
                log_error(f"HTTP错误 {e.response.status_code}: {url[:80]}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                log_warn(f"请求异常 ({url[:60]}...): {str(e)[:50]}，{delay}秒后重试")
                time.sleep(delay)
            else:
                log_error(f"请求异常，已重试{retries}次: {url[:80]} - {str(e)[:80]}")
                return None
    return None


def safe_text(element):
    """安全获取元素文本"""
    if element is None:
        return ""
    return element.get_text(strip=True)


def clean_title(title):
    """清理重复标题"""
    if not title:
        return title
    title = re.sub(r'^\d{1,2}\d{4}-\d{2}', '', title).strip()
    if len(title) > 30:
        half = len(title) // 2
        if title[:half] == title[half:]:
            title = title[:half]
    for dup_len in range(len(title)//2, 10, -1):
        if title[:dup_len] * 2 == title[:dup_len*2]:
            title = title[:dup_len]
            break
    return title


def save_cache(data, cache_key, report_date):
    """保存数据到缓存"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}_{report_date}.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        log_warn(f"缓存保存失败: {str(e)[:50]}")
        return False


def load_cache(cache_key, report_date):
    """从缓存加载数据"""
    try:
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}_{report_date}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return None


# ============================================
# 模块一：国家统计局
# ============================================
def fetch_stats_data():
    """采集国家统计局数据"""
    log_info("开始采集国家统计局数据...")
    result = {
        "source": "国家统计局",
        "source_url": STATS_URL,
        "status": "success",
        "latest_releases": [],
        "upcoming": [],
    }

    try:
        # 多源降级：首页 → 最新发布栏目
        stats_sources = [
            ("国家统计局首页", STATS_URL, STATS_URL),
            ("国家统计局最新发布", "https://www.stats.gov.cn/sj/zxfb/", "https://www.stats.gov.cn/sj/zxfb/"),
        ]
        response = None
        source_name = "国家统计局"
        base_url = STATS_URL
        for src_name, src_url, src_base in stats_sources:
            log_info(f"尝试国家统计局数据源: {src_name}")
            response = fetch_with_retry(src_url, encoding='utf-8', timeout=(8, 15), retries=2)
            if response is not None and len(response.text) > 1000:
                source_name = src_name
                base_url = src_base
                log_info(f"国家统计局数据源 {src_name} 成功")
                break
            log_warn(f"国家统计局数据源 {src_name} 失败，尝试下一个")
            random_delay(0.5, 1.0)

        if response is None:
            result["status"] = "failed"
            log_error("国家统计局所有数据源均失败")
            return result

        result["source"] = source_name
        result["source_url"] = base_url
        soup = BeautifulSoup(response.text, 'html.parser')
        release_items = []
        seen_titles = set()

        data_keywords = ['增长', '指数', '价格', '利润', '产值', '投资', '消费',
                         '收入', 'CPI', 'PPI', 'PMI', 'GDP', '人口', '就业',
                         '工业', '房地产', '进出口', '贸易', '能源', '产量',
                         '发布', '公告', '解读', '统计', '数据', '报告',
                         '流通', '生产资料', '早稻', '粮食', '国民经济',
                         '规模以上', '固定资产', '社会消费品', '居民消费',
                         '工业生产者', '采购经理', '经济发展', '新动能']

        exclude_keywords = ['开放日', '抽样调查', '会见', '代表团', '集体学习',
                          '理论学习', '党组', '监管企业', '工资总额', '信息披露',
                          '非凡', '十四五', '成就报告', '农业普查', '统计开放日',
                          '人口抽样', '习近平', '李强', '重要指示', '会谈',
                          '致电', '祝贺', '调研', '国务院常务会议', '办公厅',
                          '党政领导', '西藏', '泥石流', '灾害', '庆祝', '成立',
                          '建党', '共产党', '任免', '干部', '司长', '厅长',
                          '巡视', '巡察', '廉政', '纪检', '监察', '党建']

        for link in soup.find_all('a', href=True):
            title = safe_text(link)
            href = link.get('href', '')
            if not title or len(title) < 8 or len(title) > 80:
                continue
            title = clean_title(title)
            if title in seen_titles:
                continue
            if not any(kw in title for kw in data_keywords):
                continue
            if any(kw in title for kw in exclude_keywords):
                continue

            full_url = urljoin(base_url, href)
            date_str = ""
            parent = link.parent
            if parent:
                parent_text = parent.get_text()
                date_match = re.search(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', parent_text)
                if date_match:
                    date_str = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

            release_items.append({"title": title, "url": full_url, "date": date_str})
            seen_titles.add(title)
            if len(release_items) >= 15:
                break

        result["latest_releases"] = release_items
        log_info(f"采集到 {len(release_items)} 条最新发布")

        # 发布预告
        upcoming_items = []
        upcoming_default = [
            {"event": "每月最后一天/次月首日：PMI月度报告"},
            {"event": "每月9日左右：CPI/PPI月度报告"},
            {"event": "每月15日左右：工业增加值/固定资产投资/社会消费品零售总额"},
            {"event": "每月27日左右：工业企业利润数据"},
        ]
        for text in soup.stripped_strings:
            if any(kw in text for kw in ['预告', '日程', '发布日历']):
                parent_elem = soup.find(string=text)
                if parent_elem:
                    gp = parent_elem.find_parent()
                    if gp:
                        lines = [l.strip() for l in gp.get_text(separator='\n', strip=True).split('\n') if l.strip()]
                        for line in lines:
                            if re.search(r'\d{1,2}月\d{1,2}日', line) or re.search(r'\d{4}-\d{2}-\d{2}', line):
                                upcoming_items.append({"event": line})
                break

        result["upcoming"] = upcoming_items[:10] if upcoming_items else upcoming_default
        log_info(f"采集到 {len(result['upcoming'])} 条发布预告")

    except Exception as e:
        result["status"] = "error"
        log_error(f"国家统计局采集异常: {str(e)[:120]}")

    return result


# ============================================
# 模块二：A股主要指数（腾讯财经API）
# ============================================
def fetch_tencent_indices():
    """腾讯财经行情API（主数据源）"""
    indices_map = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
        "sh000688": "科创50",
        "sh000300": "沪深300",
    }
    codes = ",".join(indices_map.keys())
    url = f"https://qt.gtimg.cn/q={codes}"
    response = fetch_with_retry(url, encoding='gbk')
    if response is None:
        return None

    indices = {}
    for line in response.text.strip().split('\n'):
        if '=' not in line or '~' not in line:
            continue
        var_part, data_part = line.split('=', 1)
        code = var_part.replace('v_', '').strip()
        name = indices_map.get(code, code)
        data = data_part.strip().strip('"').split('~')
        if len(data) >= 35:
            try:
                current = float(data[3]) if data[3] else 0
                prev_close = float(data[4]) if data[4] else 0
                open_price = float(data[5]) if data[5] else 0
                volume = float(data[6]) if data[6] else 0
                change = float(data[31]) if data[31] else 0
                change_pct = float(data[32]) if data[32] else 0
                high = float(data[33]) if data[33] else 0
                low = float(data[34]) if data[34] else 0
                amount = 0
                if len(data) > 37 and data[37]:
                    try:
                        amount = float(data[37]) * 10000
                    except ValueError:
                        pass
                indices[name] = {
                    "code": code, "current": round(current, 2),
                    "prev_close": round(prev_close, 2), "open": round(open_price, 2),
                    "high": round(high, 2), "low": round(low, 2),
                    "change": round(change, 2), "change_pct": round(change_pct, 2),
                    "volume": volume, "amount": amount,
                }
            except (ValueError, IndexError):
                continue
    return {"indices": indices} if indices else None


def fetch_ths_indices():
    """同花顺API（备用）"""
    url = "http://d.10jqka.com.cn/v6/realhead/hs_000001/last.js"
    headers = {**HEADERS, "Referer": "https://q.10jqka.com.cn/"}
    response = fetch_with_retry(url, headers=headers)
    if response is None:
        return None
    try:
        text = response.text
        json_start = text.find('(')
        json_end = text.rfind(')')
        if json_start > 0 and json_end > json_start:
            data = json.loads(text[json_start + 1:json_end])
            items = data.get("items", {})
            current = float(items.get("10", 0))
            prev_close = float(items.get("9", 0))
            change = current - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0
            return {"indices": {
                "上证指数": {"code": "hs_000001", "current": round(current, 2),
                            "prev_close": round(prev_close, 2), "change": round(change, 2),
                            "change_pct": round(change_pct, 2)}
            }}
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return None


def fetch_market_data():
    """采集A股行情数据（多源降级）"""
    log_info("开始采集A股行情数据...")
    result = {"source": "", "status": "success", "indices": {}}

    sources = [
        ("腾讯财经API", fetch_tencent_indices),
        ("同花顺API", fetch_ths_indices),
    ]

    for source_name, fetch_func in sources:
        log_info(f"尝试数据源: {source_name}")
        try:
            data = fetch_func()
            if data and data.get("indices"):
                result["indices"] = data["indices"]
                result["source"] = source_name
                log_info(f"数据源 {source_name} 采集成功，{len(data['indices'])}个指数")
                break
            else:
                log_warn(f"数据源 {source_name} 返回空数据，尝试下一个")
        except Exception as e:
            log_warn(f"数据源 {source_name} 异常: {str(e)[:60]}，尝试下一个")

    if not result["indices"]:
        result["status"] = "failed"
        log_error("所有A股行情数据源均失败")

    return result


# ============================================
# 模块三：行业板块（新浪财经API）
# ============================================
def fetch_sector_data():
    """采集行业板块涨跌幅数据"""
    log_info("开始采集行业板块数据...")
    result = {"source": "新浪财经", "status": "success", "sectors": []}

    try:
        url = "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
        headers = {**HEADERS, "Referer": "https://finance.sina.com.cn/"}
        response = fetch_with_retry(url, headers=headers, encoding='gbk')
        if response is None:
            result["status"] = "failed"
            log_error("行业板块数据访问失败")
            return result

        # 解析 JS 变量
        text = response.text
        json_start = text.find('{')
        json_end = text.rfind('}')
        if json_start < 0 or json_end <= json_start:
            result["status"] = "failed"
            return result

        data = json.loads(text[json_start:json_end+1])
        sectors = []
        for key, value in data.items():
            if not isinstance(value, str):
                continue
            parts = value.split(',')
            if len(parts) >= 10:
                try:
                    name = parts[1] if len(parts) > 1 else key
                    change_pct = float(parts[5]) if len(parts) > 5 and parts[5] else 0
                    change = float(parts[4]) if len(parts) > 4 and parts[4] else 0
                    avg_price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
                    volume = float(parts[6]) if len(parts) > 6 and parts[6] else 0
                    amount = float(parts[7]) if len(parts) > 7 and parts[7] else 0
                    leader_stock = parts[8] if len(parts) > 8 else ""
                    leader_change = float(parts[10]) if len(parts) > 10 and parts[10] else 0

                    sectors.append({
                        "name": name,
                        "change_pct": round(change_pct, 2),
                        "change": round(change, 2),
                        "avg_price": round(avg_price, 2),
                        "volume": volume,
                        "amount": amount,
                        "leader_stock": leader_stock,
                        "leader_change": round(leader_change, 2),
                    })
                except (ValueError, IndexError):
                    continue

        # 按涨跌幅排序
        sectors.sort(key=lambda x: x["change_pct"], reverse=True)
        result["sectors"] = sectors
        result["top_gainers"] = sectors[:5]
        result["top_losers"] = sectors[-5:][::-1] if len(sectors) >= 5 else []
        log_info(f"采集到 {len(sectors)} 个行业板块，领涨: {sectors[0]['name'] if sectors else '无'}")

    except Exception as e:
        result["status"] = "error"
        log_error(f"行业板块采集异常: {str(e)[:100]}")

    return result


# ============================================
# 模块四：全球市场（东方财富API）
# ============================================
def fetch_global_market():
    """采集全球市场数据（多源降级：东方财富→新浪→腾讯）"""
    log_info("开始采集全球市场数据...")
    result = {"source": "", "status": "success", "markets": {}}

    # 数据源1：东方财富API
    def try_eastmoney():
        secids = "100.DJIA,100.NDX,100.SPX,101.GC00Y,101.CL00Y,133.USDCNH"
        url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids={secids}&fields=f2,f3,f4,f12,f14"
        response = fetch_with_retry(url, timeout=(8, 15), retries=2)
        if response is None:
            return None
        data = response.json().get("data", {})
        diff = data.get("diff", [])
        if not diff:
            return None
        name_map = {
            "DJIA": "道琼斯", "NDX": "纳斯达克", "SPX": "标普500",
            "GC00Y": "COMEX黄金", "CL00Y": "WTI原油", "USDCNH": "美元兑离岸人民币"
        }
        markets = {}
        for item in diff:
            code = item.get("f12", "")
            name = name_map.get(code, item.get("f14", code))
            markets[name] = {
                "code": code, "price": item.get("f2", 0),
                "change": item.get("f4", 0), "change_pct": item.get("f3", 0),
            }
        return markets

    # 数据源2：新浪财经全球行情API
    def try_sina():
        symbols = "gb_dji,gb_ixic,gb_inx,hf_GC,hf_CL,fx_susdcnh"
        url = f"https://hq.sinajs.cn/list={symbols}"
        headers = {"Referer": "https://finance.sina.com.cn/"}
        response = fetch_with_retry(url, headers=headers, timeout=(8, 15), retries=2, encoding='gbk')
        if response is None:
            return None
        name_map = {
            "gb_dji": "道琼斯", "gb_ixic": "纳斯达克", "gb_inx": "标普500",
            "hf_GC": "COMEX黄金", "hf_CL": "WTI原油", "fx_susdcnh": "美元兑离岸人民币"
        }
        markets = {}
        for line in response.text.split('\n'):
            line = line.strip()
            if not line or '=' not in line:
                continue
            var_part, val_part = line.split('=', 1)
            symbol = var_part.replace('var hq_str_', '').strip()
            name = name_map.get(symbol)
            if not name:
                continue
            vals = val_part.strip('";').split(',')
            if len(vals) < 3:
                continue
            try:
                if symbol.startswith('gb_'):
                    price = float(vals[1])
                    change = float(vals[4]) if len(vals) > 4 else 0
                    change_pct = float(vals[2]) if len(vals) > 2 else 0
                elif symbol.startswith('hf_'):
                    price = float(vals[0])
                    change = float(vals[1]) if len(vals) > 1 else 0
                    change_pct = float(vals[2]) if len(vals) > 2 else 0
                else:
                    price = float(vals[1]) if len(vals) > 1 else float(vals[0])
                    change = 0
                    change_pct = 0
                markets[name] = {"code": symbol, "price": price, "change": change, "change_pct": change_pct}
            except (ValueError, IndexError):
                continue
        return markets if markets else None

    # 数据源3：腾讯财经全球行情
    def try_tencent():
        symbols = "usDJI,usIXIC,usINX,hf_GC,hf_CL,fx_susdcnh"
        url = f"https://qt.gtimg.cn/q={symbols}"
        headers = {"Referer": "https://gu.qq.com/"}
        response = fetch_with_retry(url, headers=headers, timeout=(8, 15), retries=2, encoding='gbk')
        if response is None:
            return None
        name_map = {
            "usDJI": "道琼斯", "usIXIC": "纳斯达克", "usINX": "标普500",
            "hf_GC": "COMEX黄金", "hf_CL": "WTI原油", "fx_susdcnh": "美元兑离岸人民币"
        }
        markets = {}
        for line in response.text.split(';'):
            line = line.strip()
            if not line or '~' not in line or '=' not in line:
                continue
            # 解析 v_usDJI="200~道琼斯~..." 格式
            var_part, val_part = line.split('=', 1)
            # 提取symbol：v_usDJI -> usDJI
            symbol = var_part.replace('var ', '').replace('v_', '').strip()
            # 去掉值部分的引号
            val_part = val_part.strip().strip('"')
            name = name_map.get(symbol)
            if not name:
                continue
            parts = val_part.split('~')
            if len(parts) < 33:
                continue
            try:
                price = float(parts[3]) if len(parts) > 3 else 0
                # 腾讯财经格式：parts[31]=涨跌额, parts[32]=涨跌幅
                change = float(parts[31]) if len(parts) > 31 else 0
                change_pct = float(parts[32]) if len(parts) > 32 else 0
                if price > 0:
                    markets[name] = {"code": symbol, "price": price, "change": change, "change_pct": change_pct}
            except (ValueError, IndexError):
                continue
        return markets if markets else None

    # 按优先级尝试各数据源（腾讯财经优先，因为当前环境东方财富和新浪财经可能无法访问）
    sources = [
        ("腾讯财经", try_tencent),
        ("东方财富", try_eastmoney),
        ("新浪财经", try_sina),
    ]

    for source_name, source_func in sources:
        try:
            log_info(f"尝试全球市场数据源: {source_name}")
            markets = source_func()
            if markets and len(markets) >= 3:
                result["source"] = source_name
                result["markets"] = markets
                log_info(f"全球市场数据源 {source_name} 成功，{len(markets)}个指标")
                return result
            else:
                log_warn(f"全球市场数据源 {source_name} 返回数据不足")
        except Exception as e:
            log_warn(f"全球市场数据源 {source_name} 异常: {str(e)[:60]}")
        random_delay(0.5, 1.0)

    result["status"] = "failed"
    log_error("全球市场所有数据源均失败")
    return result


# ============================================
# 模块五：个股排行（新浪财经API）
# ============================================
def fetch_stock_ranking():
    """采集个股排行数据（涨幅榜、跌幅榜、成交额榜）"""
    log_info("开始采集个股排行数据...")
    result = {
        "source": "新浪财经API",
        "status": "success",
        "top_gainers": [],   # 涨幅榜
        "top_losers": [],     # 跌幅榜
        "top_volume": [],     # 成交额榜
    }

    base_url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    headers = {"Referer": "https://finance.sina.com.cn/"}

    def fetch_ranking(sort_field, asc, count=10):
        """获取排行数据"""
        url = f"{base_url}?page=1&num={count}&sort={sort_field}&asc={asc}&node=hs_a&symbol=&_s_r_a=page"
        try:
            response = fetch_with_retry(url, headers=headers, timeout=(8, 15), retries=2, encoding='gbk')
            if response is None:
                return []
            text = response.text.strip()
            if not text or text == 'null':
                return []
            # 新浪财经返回的是标准JSON，直接解析
            data = json.loads(text)
            stocks = []
            for item in data[:count]:
                stock = {
                    "code": item.get("code", ""),
                    "name": item.get("name", ""),
                    "price": float(item.get("trade", 0)),
                    "change": float(item.get("pricechange", 0)),
                    "change_pct": float(item.get("changepercent", 0)),
                    "volume": int(item.get("volume", 0)),
                    "amount": float(item.get("amount", 0)),
                    "turnover": float(item.get("turnoverratio", 0)),
                    "pe": float(item.get("per", 0)),
                    "pb": float(item.get("pb", 0)),
                    "market_cap": float(item.get("mktcap", 0)),
                }
                stocks.append(stock)
            return stocks
        except Exception as e:
            log_warn(f"获取排行数据失败 ({sort_field}): {str(e)[:60]}")
            return []

    # 涨幅榜（按涨跌幅降序）
    log_info("获取涨幅榜...")
    result["top_gainers"] = fetch_ranking("changepercent", 0, 10)
    log_info(f"涨幅榜: {len(result['top_gainers'])}只")

    # 跌幅榜（按涨跌幅升序）
    log_info("获取跌幅榜...")
    result["top_losers"] = fetch_ranking("changepercent", 1, 10)
    log_info(f"跌幅榜: {len(result['top_losers'])}只")

    # 成交额榜（按成交额降序）
    log_info("获取成交额榜...")
    result["top_volume"] = fetch_ranking("amount", 0, 10)
    log_info(f"成交额榜: {len(result['top_volume'])}只")

    if not result["top_gainers"] and not result["top_losers"] and not result["top_volume"]:
        result["status"] = "failed"
        log_error("个股排行所有数据源均失败")
    else:
        log_info(f"个股排行采集成功: 涨幅{len(result['top_gainers'])}只, 跌幅{len(result['top_losers'])}只, 成交额{len(result['top_volume'])}只")

    return result


# ============================================
# 模块六：财经新闻（新浪财经）
# ============================================
def fetch_news_data():
    """采集新浪财经新闻"""
    log_info("开始采集新浪财经新闻...")
    result = {
        "source": "新浪财经", "source_url": SINA_URL,
        "status": "success", "top_news": [],
        "categories": {"international": [], "macro": [], "company": [], "other": []},
    }

    try:
        # 多源降级：新浪财经 → 东方财富
        news_sources = [
            ("新浪财经", SINA_URL, SINA_URL, 'utf-8'),
            ("东方财富", "https://finance.eastmoney.com/", "https://finance.eastmoney.com/", 'utf-8'),
        ]
        response = None
        source_name = "新浪财经"
        base_url = SINA_URL
        for src_name, src_url, src_base, src_enc in news_sources:
            log_info(f"尝试财经新闻数据源: {src_name}")
            response = fetch_with_retry(src_url, encoding=src_enc, timeout=(8, 15), retries=2)
            if response is not None and len(response.text) > 2000:
                source_name = src_name
                base_url = src_base
                log_info(f"财经新闻数据源 {src_name} 成功")
                break
            log_warn(f"财经新闻数据源 {src_name} 失败，尝试下一个")
            random_delay(0.5, 1.0)

        if response is None:
            result["status"] = "failed"
            log_error("财经新闻所有数据源均失败")
            return result

        result["source"] = source_name
        result["source_url"] = base_url
        soup = BeautifulSoup(response.text, 'html.parser')
        news_items = []
        seen = set()

        exclude_keywords = ['登录', '注册', '客户端', '下载', '广告', '更多', '首页',
                            '视频', '直播', '图片', '专题', '滚动', 'level2',
                            '十档', '行情', 'APP', '微博', '博客', '论坛',
                            '股吧', '基金吧', '财富号', '搜索', '帮助', '关于']

        international_kw = ['美国', '美联储', '特朗普', '伊朗', '以色列', '俄乌', '俄罗斯',
                           '乌克兰', '欧盟', '欧洲', '日本', '韩国', '中东', '地缘', '军事',
                           '北约', '联合国', 'G20', 'G7', '外交', '国际', '全球', '海外']
        macro_kw = ['央行', '货币政策', '利率', '降息', '加息', '财政', '税收', 'GDP',
                   'CPI', 'PPI', 'PMI', '经济', '增长', '通胀', '就业', '监管', '政策',
                   '国务院', '发改委', '财政部', '商务部', '证监会', '银保监', '宏观']
        company_kw = ['公司', '股份', '集团', '控股', '有限', '科技', '汽车', '医药',
                     '银行', '证券', '保险', '地产', '能源', '芯片', 'AI', '人工智能',
                     '新能源', '光伏', '锂电', '半导体', '业绩', '财报', '营收', '利润',
                     '上市', 'IPO', '并购', '重组', '分红', '回购']

        # 新闻重要性评分关键词
        high_priority_kw = ['央行', '降息', '加息', '美联储', 'GDP', 'CPI', 'PPI', 'PMI',
                           '国务院', '证监会', 'IPO', '退市', '爆雷', '崩盘', '暴涨', '暴跌',
                           '万亿', '千亿', '战争', '冲突', '制裁', '关税', '贸易战', '疫情',
                           '新能源', '人工智能', '芯片', '半导体', '光伏', '锂电']
        medium_priority_kw = ['政策', '监管', '法规', '改革', '规划', '意见', '通知',
                             '业绩', '财报', '营收', '利润', '亏损', '盈利', '增长', '下滑',
                             '并购', '重组', '分红', '回购', '增持', '减持', '质押', '爆仓',
                             '融资', '融券', '北向', '南向', '主力', '机构', '外资']
        low_priority_kw = ['公司', '股份', '集团', '控股', '有限', '科技', '汽车', '医药',
                          '银行', '证券', '保险', '地产', '能源']

        def calc_news_importance(title):
            """计算新闻重要性评分（0-10分）"""
            score = 0
            # 高优先级关键词
            high_count = sum(1 for kw in high_priority_kw if kw in title)
            score += min(high_count * 3, 6)
            # 中优先级关键词
            medium_count = sum(1 for kw in medium_priority_kw if kw in title)
            score += min(medium_count * 2, 4)
            # 低优先级关键词
            low_count = sum(1 for kw in low_priority_kw if kw in title)
            score += min(low_count * 1, 2)
            # 标题长度适中
            if 15 <= len(title) <= 40:
                score += 1
            # 包含数字或百分比
            import re as re_news
            if re_news.search(r'\d+(\.\d+)?%|\d+亿|\d+万|\d+元', title):
                score += 1
            return min(score, 10)

        for link in soup.find_all('a', href=True):
            title = safe_text(link)
            href = link.get('href', '')
            if not title or len(title) < 10 or len(title) > 100:
                continue
            if title in seen:
                continue
            if not href.startswith('http'):
                href = urljoin(base_url, href)
            # 根据数据源动态检查域名
            if 'sina' in base_url:
                if not any(d in href for d in ['sina.com.cn', 'finance.sina']):
                    continue
            elif 'eastmoney' in base_url:
                if not any(d in href for d in ['eastmoney.com']):
                    continue
            if any(kw in title for kw in exclude_keywords):
                continue

            item = {"title": title, "url": href, "importance": calc_news_importance(title)}
            news_items.append(item)
            seen.add(title)

            if any(kw in title for kw in international_kw):
                result["categories"]["international"].append(item)
            elif any(kw in title for kw in macro_kw):
                result["categories"]["macro"].append(item)
            elif any(kw in title for kw in company_kw):
                result["categories"]["company"].append(item)
            else:
                result["categories"]["other"].append(item)

            if len(news_items) >= 50:
                break

        # 按重要性排序，生成重点新闻
        news_items_sorted = sorted(news_items, key=lambda x: x.get("importance", 0), reverse=True)
        result["top_news"] = news_items_sorted[:15]
        result["highlight_news"] = news_items_sorted[:5]  # 最重要的5条
        result["total_count"] = len(news_items)
        log_info(f"采集到 {len(news_items)} 条新闻 "
                 f"(国际:{len(result['categories']['international'])}, "
                 f"宏观:{len(result['categories']['macro'])}, "
                 f"公司:{len(result['categories']['company'])}, "
                 f"其他:{len(result['categories']['other'])})")

    except Exception as e:
        result["status"] = "error"
        log_error(f"新浪财经采集异常: {str(e)[:120]}")

    return result


# ============================================
# 主函数
# ============================================
def main():
    parser = argparse.ArgumentParser(description='每日财经日报数据采集脚本（增强版）')
    parser.add_argument('--output', '-o', help='输出JSON文件路径')
    parser.add_argument('--date', '-d', help='报告日期（YYYY-MM-DD，默认今天）')
    parser.add_argument('--no-cache', action='store_true', help='不使用历史缓存')
    args = parser.parse_args()

    report_date = args.date or datetime.now().strftime('%Y-%m-%d')
    output_path = args.output or f"output/data_{report_date}.json"

    # 重置全局变量，避免多次运行时错误累积
    global ERRORS, LOGS
    ERRORS = []
    LOGS = []

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    log_info("=" * 60)
    log_info(f"每日财经日报数据采集开始（增强版）")
    log_info(f"报告日期: {report_date}")
    log_info(f"输出文件: {output_path}")
    log_info("=" * 60)

    start_time = time.time()

    # 健康检查：快速测试各数据源可用性
    log_info("开始数据源健康检查...")
    health_check_urls = {
        "国家统计局": STATS_URL,
        "新浪财经": SINA_URL,
        "腾讯财经": "https://qt.gtimg.cn/q=sh000001",
        "东方财富": "https://finance.eastmoney.com/",
    }
    health_status = {}
    for name, url in health_check_urls.items():
        try:
            resp = SESSION.get(url, headers=get_random_headers(), timeout=(5, 8), allow_redirects=True)
            health_status[name] = "ok" if resp.status_code == 200 and len(resp.text) > 500 else f"http_{resp.status_code}"
        except Exception as e:
            health_status[name] = f"error_{str(e)[:30]}"
        log_info(f"  健康检查 {name}: {health_status[name]}")
    random_delay(0.3, 0.5)

    # 采集五大模块
    stats_data = fetch_stats_data()
    market_data = fetch_market_data()
    sector_data = fetch_sector_data()
    global_data = fetch_global_market()
    stock_ranking = fetch_stock_ranking()
    news_data = fetch_news_data()

    # 历史数据对比（环比）
    comparison = {}
    if not args.no_cache:
        yesterday = (datetime.strptime(report_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        prev_market = load_cache("market", yesterday)
        if prev_market and prev_market.get("indices"):
            comparison["market_vs_yesterday"] = {
                "prev_date": yesterday,
                "note": "可用于环比对比"
            }

    # 缓存当天数据
    save_cache(market_data, "market", report_date)
    save_cache(stats_data, "stats", report_date)

    # 整合结果
    elapsed = round(time.time() - start_time, 2)
    result = {
        "collect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "report_date": report_date,
        "elapsed_seconds": elapsed,
        "stats": stats_data,
        "market": market_data,
        "sectors": sector_data,
        "global_market": global_data,
        "stock_ranking": stock_ranking,
        "news": news_data,
        "comparison": comparison,
        "errors": ERRORS,
        "summary": {
            "stats_status": stats_data.get("status", "unknown"),
            "stats_releases": len(stats_data.get("latest_releases", [])),
            "market_status": market_data.get("status", "unknown"),
            "market_source": market_data.get("source", ""),
            "market_indices": len(market_data.get("indices", {})),
            "sector_status": sector_data.get("status", "unknown"),
            "sector_count": len(sector_data.get("sectors", [])),
            "global_status": global_data.get("status", "unknown"),
            "global_count": len(global_data.get("markets", {})),
            "stock_ranking_status": stock_ranking.get("status", "unknown"),
            "stock_gainers_count": len(stock_ranking.get("top_gainers", [])),
            "stock_losers_count": len(stock_ranking.get("top_losers", [])),
            "news_status": news_data.get("status", "unknown"),
            "news_count": news_data.get("total_count", len(news_data.get("top_news", []))),
            "total_errors": len(ERRORS),
            "elapsed_seconds": elapsed,
            "health_check": health_status,
        },
    }

    # 写入 JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log_info(f"数据已写入: {output_path}")
    except Exception as e:
        log_error(f"写入JSON失败: {str(e)}")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    # 写入日志文件
    try:
        log_file = os.path.join(LOG_DIR, f"collect_{report_date}.log")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(LOGS))
    except Exception:
        pass

    # 打印摘要
    log_info("=" * 60)
    log_info("采集摘要:")
    s = result["summary"]
    log_info(f"  国家统计局: {s['stats_status']} - {s['stats_releases']}条发布")
    log_info(f"  A股行情: {s['market_status']} - {s['market_source']} - {s['market_indices']}个指数")
    log_info(f"  行业板块: {s['sector_status']} - {s['sector_count']}个板块")
    log_info(f"  全球市场: {s['global_status']} - {s['global_count']}个指标")
    log_info(f"  财经新闻: {s['news_status']} - {s['news_count']}条新闻")
    log_info(f"  错误数: {s['total_errors']}")
    log_info(f"  耗时: {s['elapsed_seconds']}秒")
    log_info("=" * 60)

    if ERRORS:
        sys.exit(1)


if __name__ == "__main__":
    main()
