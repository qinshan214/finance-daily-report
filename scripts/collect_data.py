#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日财经日报数据采集脚本

采集三大数据源，输出结构化 JSON：
1. 国家统计局 - 最新发布数据 + 发布预告
2. A股行情 - 主要指数 + 板块变化 + 资金流向 + 全球市场（多源降级）
3. 新浪财经 - 重要新闻列表

使用方式：
    python3 collect_data.py [--output output.json] [--date YYYY-MM-DD]

输出 JSON 结构：
{
    "collect_time": "2026-08-28 20:00:00",
    "report_date": "2026-08-28",
    "stats": { ... },
    "market": { ... },
    "news": { ... },
    "errors": [...]
}
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import argparse
import os
import sys
from datetime import datetime
from urllib.parse import urljoin

# ============================================
# 配置
# ============================================
DEFAULT_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 2  # 基础重试延迟（秒），指数退避

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 数据源 URL
STATS_URL = "https://www.stats.gov.cn/"
EASTMONEY_URL = "https://www.eastmoney.com/"
SINA_URL = "https://finance.sina.com.cn/"

# 错误收集
ERRORS = []


# ============================================
# 工具函数
# ============================================
def log(level, message):
    """打印日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def log_info(msg):
    log("INFO", msg)


def log_warn(msg):
    log("WARN", msg)


def log_error(msg):
    log("ERROR", msg)
    ERRORS.append(msg)


def fetch_with_retry(url, headers=None, timeout=DEFAULT_TIMEOUT, retries=MAX_RETRIES, encoding=None):
    """
    带重试的 HTTP GET 请求
    返回 Response 对象，失败返回 None
    """
    merged_headers = {**HEADERS, **(headers or {})}
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=merged_headers, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            if encoding:
                response.encoding = encoding
            else:
                # 自动检测编码
                if response.encoding == 'ISO-8859-1':
                    response.encoding = response.apparent_encoding or 'utf-8'
            return response
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                log_warn(f"请求超时 ({url})，{delay}秒后重试 ({attempt+1}/{retries})")
                time.sleep(delay)
            else:
                log_error(f"请求超时，已重试{retries}次: {url}")
                return None
        except requests.exceptions.HTTPError as e:
            if attempt < retries - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                log_warn(f"HTTP错误 {e.response.status_code} ({url})，{delay}秒后重试")
                time.sleep(delay)
            else:
                log_error(f"HTTP错误 {e.response.status_code}: {url}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                log_warn(f"请求异常 ({url}): {str(e)[:50]}，{delay}秒后重试")
                time.sleep(delay)
            else:
                log_error(f"请求异常，已重试{retries}次: {url} - {str(e)[:100]}")
                return None
    return None


def safe_text(element):
    """安全获取元素文本，去除多余空白"""
    if element is None:
        return ""
    return element.get_text(strip=True)


# ============================================
# 模块一：国家统计局数据采集
# ============================================
def fetch_stats_data():
    """
    采集国家统计局数据
    返回 dict: {latest_releases: [...], upcoming: [...], source: str, status: str}
    """
    log_info("开始采集国家统计局数据...")
    result = {
        "source": "国家统计局",
        "source_url": STATS_URL,
        "status": "success",
        "latest_releases": [],
        "upcoming": [],
    }

    try:
        response = fetch_with_retry(STATS_URL, encoding='utf-8')
        if response is None:
            result["status"] = "failed"
            log_error("国家统计局首页访问失败")
            return result

        soup = BeautifulSoup(response.text, 'html.parser')

        # 采集最新发布列表
        # 国家统计局首页的"数据发布与解读"区域
        release_items = []

        # 尝试多种选择器定位最新发布
        # 方式1：查找包含日期和标题的列表项
        all_links = soup.find_all('a', href=True)
        seen_titles = set()

        for link in all_links:
            title = safe_text(link)
            href = link.get('href', '')

            # 过滤：标题长度合理，且包含数据相关关键词
            if not title or len(title) < 8 or len(title) > 80:
                continue
            if title in seen_titles:
                continue

            # 数据发布相关关键词（必须包含）
            data_keywords = ['增长', '指数', '价格', '利润', '产值', '投资', '消费',
                             '收入', 'CPI', 'PPI', 'PMI', 'GDP', '人口', '就业',
                             '工业', '房地产', '进出口', '贸易', '能源', '产量',
                             '发布', '公告', '解读', '统计', '数据', '报告',
                             '流通', '生产资料', '早稻', '粮食', '国民经济',
                             '规模以上', '固定资产', '社会消费品', '居民消费',
                             '工业生产者', '采购经理', '经济发展', '新动能']

            # 排除关键词（专题、新闻、通知、会议、人事等非数据发布内容）
            exclude_keywords = ['开放日', '抽样调查', '会见', '代表团', '集体学习',
                              '理论学习', '党组', '监管企业', '工资总额', '信息披露',
                              '非凡', '十四五', '成就报告', '农业普查', '统计开放日',
                              '人口抽样', '习近平', '李强', '重要指示', '会谈',
                              '致电', '祝贺', '调研', '国务院常务会议', '办公厅',
                              '党政领导', '西藏', '泥石流', '灾害', '庆祝', '成立',
                              '建党', '共产党', '任免', '干部', '司长', '厅长',
                              '巡视', '巡察', '廉政', '纪检', '监察', '党建',
                              '共青团', '妇联', '工会', '统战', '民族', '宗教',
                              '培训', '学习班', '研讨班', '座谈会', '报告会',
                              '表彰', '奖励', '荣誉', '称号', '先进', '优秀']

            if not any(kw in title for kw in data_keywords):
                continue
            if any(kw in title for kw in exclude_keywords):
                continue

            # 清理重复标题（国家统计局页面标题经常重复2-3次）
            import re
            # 去除开头的日期数字（如"272026-08"）
            title = re.sub(r'^\d{1,2}\d{4}-\d{2}', '', title).strip()
            # 如果标题长度>30且前半部分等于后半部分，取前半部分
            if len(title) > 30:
                half = len(title) // 2
                if title[:half] == title[half:]:
                    title = title[:half]
                elif title[:half-2] == title[half-2:half*2-4]:
                    title = title[:half-2]
            # 再次检查是否有连续重复
            for dup_len in range(len(title)//2, 10, -1):
                if title[:dup_len] * 2 == title[:dup_len*2]:
                    title = title[:dup_len]
                    break

            # 构建完整URL
            full_url = urljoin(STATS_URL, href)

            # 查找相邻的日期元素
            date_str = ""
            parent = link.parent
            if parent:
                # 查找父元素中的日期文本
                parent_text = parent.get_text()
                import re
                date_match = re.search(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', parent_text)
                if date_match:
                    date_str = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

            release_items.append({
                "title": title,
                "url": full_url,
                "date": date_str,
            })
            seen_titles.add(title)

            if len(release_items) >= 15:
                break

        result["latest_releases"] = release_items
        log_info(f"采集到 {len(release_items)} 条最新发布")

        # 采集发布预告
        upcoming_items = []
        # 查找页面中的发布预告区域
        upcoming_keywords = ['预告', '日程', '发布日历', '发布时间']

        for text in soup.stripped_strings:
            if any(kw in text for kw in upcoming_keywords):
                # 查找附近的日期和事件
                parent_elem = soup.find(string=text)
                if parent_elem:
                    grandparent = parent_elem.find_parent()
                    if grandparent:
                        upcoming_text = grandparent.get_text(separator='\n', strip=True)
                        lines = [l.strip() for l in upcoming_text.split('\n') if l.strip()]
                        for line in lines:
                            import re
                            if re.search(r'\d{1,2}月\d{1,2}日', line) or re.search(r'\d{4}-\d{2}-\d{2}', line):
                                upcoming_items.append({"event": line})
                break

        # 如果没找到预告区域，用默认预告
        if not upcoming_items:
            upcoming_items = [
                {"event": "每月最后一天/次月首日：PMI月度报告"},
                {"event": "每月9日左右：CPI/PPI月度报告"},
                {"event": "每月15日左右：工业增加值/固定资产投资/社会消费品零售总额"},
            ]

        result["upcoming"] = upcoming_items[:10]
        log_info(f"采集到 {len(upcoming_items)} 条发布预告")

    except Exception as e:
        result["status"] = "error"
        log_error(f"国家统计局采集异常: {str(e)[:150]}")

    return result


# ============================================
# 模块二：A股行情数据采集（多源降级）
# ============================================
def fetch_market_data():
    """
    采集A股行情数据（多源降级）
    主源：新浪财经行情API
    备用1：东方财富行情API
    备用2：同花顺API
    返回 dict
    """
    log_info("开始采集A股行情数据...")
    result = {
        "source": "",
        "status": "success",
        "indices": {},
        "global_market": {},
        "notes": [],
    }

    # 尝试多个数据源
    sources = [
        ("腾讯财经API", fetch_tencent_indices),
        ("同花顺API", fetch_ths_indices),
        ("新浪财经API", fetch_sina_indices),
    ]

    for source_name, fetch_func in sources:
        log_info(f"尝试数据源: {source_name}")
        try:
            data = fetch_func()
            if data and data.get("indices"):
                result["indices"] = data["indices"]
                result["global_market"] = data.get("global_market", {})
                result["source"] = source_name
                log_info(f"数据源 {source_name} 采集成功")
                break
            else:
                log_warn(f"数据源 {source_name} 返回空数据，尝试下一个")
        except Exception as e:
            log_warn(f"数据源 {source_name} 异常: {str(e)[:80]}，尝试下一个")

    if not result["indices"]:
        result["status"] = "failed"
        log_error("所有A股行情数据源均失败")

    return result


def fetch_tencent_indices():
    """腾讯财经行情API（主数据源，稳定可靠）"""
    # 腾讯行情接口：https://qt.gtimg.cn/q=sh000001,sz399001,...
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
                volume = float(data[6]) if data[6] else 0  # 手
                change = float(data[31]) if data[31] else 0
                change_pct = float(data[32]) if data[32] else 0
                high = float(data[33]) if data[33] else 0
                low = float(data[34]) if data[34] else 0
                # 成交额（万元）在字段37附近
                amount = 0
                if len(data) > 37 and data[37]:
                    try:
                        amount = float(data[37]) * 10000  # 转元
                    except ValueError:
                        pass

                indices[name] = {
                    "code": code,
                    "current": round(current, 2),
                    "prev_close": round(prev_close, 2),
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": volume,
                    "amount": amount,
                }
            except (ValueError, IndexError):
                continue

    return {"indices": indices, "global_market": {}}


def fetch_sina_indices():
    """新浪财经行情API"""
    # 新浪行情接口：http://hq.sinajs.cn/list=sh000001,sz399001,sz399006,sh000688,sh000300
    indices_map = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
        "sh000688": "科创50",
        "sh000300": "沪深300",
    }

    codes = ",".join(indices_map.keys())
    url = f"http://hq.sinajs.cn/list={codes}"
    headers = {**HEADERS, "Referer": "https://finance.sina.com.cn/"}

    response = fetch_with_retry(url, headers=headers, encoding='gbk')
    if response is None:
        return None

    indices = {}
    for line in response.text.strip().split('\n'):
        if '=' not in line:
            continue
        var_part, data_part = line.split('=', 1)
        code = var_part.replace('var hq_str_', '').strip()
        name = indices_map.get(code, code)
        data = data_part.strip().strip('"').split(',')

        if len(data) >= 4:
            try:
                current = float(data[3]) if data[3] else 0
                prev_close = float(data[2]) if data[2] else 0
                change = current - prev_close if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
                volume = float(data[8]) if len(data) > 8 and data[8] else 0
                amount = float(data[9]) if len(data) > 9 and data[9] else 0

                indices[name] = {
                    "code": code,
                    "current": round(current, 2),
                    "prev_close": round(prev_close, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": volume,
                    "amount": amount,
                }
            except (ValueError, IndexError):
                continue

    # 全球市场（简化，用固定的几个）
    global_market = {
        "note": "全球市场数据需额外API，此处仅采集A股主要指数",
    }

    return {"indices": indices, "global_market": global_market}


def fetch_eastmoney_indices():
    """东方财富行情API"""
    # 东方财富行情接口
    indices_config = [
        ("1.000001", "上证指数"),
        ("0.399001", "深证成指"),
        ("0.399006", "创业板指"),
        ("1.000688", "科创50"),
        ("1.000300", "沪深300"),
    ]

    indices = {}
    for secid, name in indices_config:
        url = (f"http://push2.eastmoney.com/api/qt/stock/get?"
               f"secid={secid}&fields=f43,f44,f45,f46,f47,f48,f60,f170")
        response = fetch_with_retry(url, headers=HEADERS)
        if response is None:
            continue

        try:
            data = response.json().get("data", {})
            if not data:
                continue

            # 东方财富数据需要除以100（价格类）
            current = data.get("f43", 0) / 100 if data.get("f43") else 0
            change = data.get("f169", 0) / 100 if data.get("f169") else 0
            change_pct = data.get("f170", 0) / 100 if data.get("f170") else 0
            volume = data.get("f47", 0)
            amount = data.get("f48", 0)

            indices[name] = {
                "code": secid,
                "current": round(current, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "volume": volume,
                "amount": amount,
            }
        except (ValueError, KeyError, json.JSONDecodeError):
            continue

    return {"indices": indices, "global_market": {}}


def fetch_ths_indices():
    """同花顺行情API"""
    # 同花顺实时行情API
    url = "http://d.10jqka.com.cn/v6/realhead/hs_000001/last.js"
    headers = {**HEADERS, "Referer": "https://q.10jqka.com.cn/"}

    response = fetch_with_retry(url, headers=headers)
    if response is None:
        return None

    try:
        # 同花顺返回 JSONP 格式，需要解析
        text = response.text
        # 提取 JSON 部分
        json_start = text.find('(')
        json_end = text.rfind(')')
        if json_start > 0 and json_end > json_start:
            json_str = text[json_start + 1:json_end]
            data = json.loads(json_str)
            items = data.get("items", {})

            # 同花顺字段编码（部分已知）
            # 10: 最新价, 7: 最高, 8: 最低, 9: 昨收
            current = float(items.get("10", 0))
            prev_close = float(items.get("9", 0))
            change = current - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            indices = {
                "上证指数": {
                    "code": "hs_000001",
                    "current": round(current, 2),
                    "prev_close": round(prev_close, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                }
            }
            return {"indices": indices, "global_market": {}}
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    return None


# ============================================
# 模块三：新浪财经新闻采集
# ============================================
def fetch_news_data():
    """
    采集新浪财经新闻
    返回 dict: {top_news: [...], categories: {...}, source: str, status: str}
    """
    log_info("开始采集新浪财经新闻...")
    result = {
        "source": "新浪财经",
        "source_url": SINA_URL,
        "status": "success",
        "top_news": [],
        "categories": {
            "international": [],
            "macro": [],
            "company": [],
            "other": [],
        },
    }

    try:
        response = fetch_with_retry(SINA_URL, encoding='utf-8')
        if response is None:
            result["status"] = "failed"
            log_error("新浪财经首页访问失败")
            return result

        soup = BeautifulSoup(response.text, 'html.parser')

        # 采集新闻链接
        news_items = []
        seen = set()

        all_links = soup.find_all('a', href=True)
        for link in all_links:
            title = safe_text(link)
            href = link.get('href', '')

            # 过滤
            if not title or len(title) < 10 or len(title) > 100:
                continue
            if title in seen:
                continue
            if not href.startswith('http'):
                href = urljoin(SINA_URL, href)

            # 只保留财经新闻相关链接
            if not any(domain in href for domain in ['sina.com.cn', 'finance.sina']):
                continue

            # 排除导航、广告、客户端下载等
            exclude_keywords = ['登录', '注册', '客户端', '下载', '广告', '更多', '首页',
                                '视频', '直播', '图片', '专题', '滚动', 'level2',
                                '十档', '行情', 'APP', '微博', '博客', '论坛',
                                '股吧', '基金吧', '财富号', '搜索', '帮助', '关于',
                                '联系我们', '隐私', '条款', '版权', '违法', '举报',
                                '网站地图', '手机版', '电脑版', '扫码', '二维码']
            if any(kw in title for kw in exclude_keywords):
                continue

            # 只保留真正的新闻文章链接（包含日期或doc/）
            if not any(pattern in href for pattern in ['/doc-', '/c/', '/article/', 'news.sina']):
                # 但允许 finance.sina.com.cn 的链接
                if 'finance.sina.com.cn' not in href:
                    continue

            news_items.append({
                "title": title,
                "url": href,
            })
            seen.add(title)

            if len(news_items) >= 50:
                break

        # 分类（简单关键词匹配）
        international_kw = ['美国', '美联储', '特朗普', '伊朗', '以色列', '俄乌', '俄罗斯',
                           '乌克兰', '欧盟', '欧洲', '日本', '韩国', '中东', '地缘', '军事',
                           '北约', '联合国', 'G20', 'G7', '外交', '国际']
        macro_kw = ['央行', '货币政策', '利率', '降息', '加息', '财政', '税收', 'GDP',
                   'CPI', 'PPI', 'PMI', '经济', '增长', '通胀', '就业', '监管', '政策',
                   '国务院', '发改委', '财政部', '商务部', '证监会', '银保监']
        company_kw = ['公司', '股份', '集团', '控股', '有限', '科技', '汽车', '医药',
                     '银行', '证券', '保险', '地产', '能源', '芯片', 'AI', '人工智能',
                     '新能源', '光伏', '锂电', '半导体', '业绩', '财报', '营收', '利润',
                     '上市', 'IPO', '并购', '重组', '分红', '回购']

        for item in news_items:
            title = item["title"]
            if any(kw in title for kw in international_kw):
                result["categories"]["international"].append(item)
            elif any(kw in title for kw in macro_kw):
                result["categories"]["macro"].append(item)
            elif any(kw in title for kw in company_kw):
                result["categories"]["company"].append(item)
            else:
                result["categories"]["other"].append(item)

        # Top 新闻（取前15条，不分类）
        result["top_news"] = news_items[:15]

        log_info(f"采集到 {len(news_items)} 条新闻 "
                 f"(国际:{len(result['categories']['international'])}, "
                 f"宏观:{len(result['categories']['macro'])}, "
                 f"公司:{len(result['categories']['company'])}, "
                 f"其他:{len(result['categories']['other'])})")

    except Exception as e:
        result["status"] = "error"
        log_error(f"新浪财经采集异常: {str(e)[:150]}")

    return result


# ============================================
# 主函数
# ============================================
def main():
    parser = argparse.ArgumentParser(description='每日财经日报数据采集脚本')
    parser.add_argument('--output', '-o', help='输出JSON文件路径（默认 output/data_YYYY-MM-DD.json）')
    parser.add_argument('--date', '-d', help='报告日期（YYYY-MM-DD，默认今天）')
    args = parser.parse_args()

    report_date = args.date or datetime.now().strftime("%Y-%m-%d")
    output_path = args.output or f"output/data_{report_date}.json"

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    log_info("=" * 60)
    log_info(f"每日财经日报数据采集开始")
    log_info(f"报告日期: {report_date}")
    log_info(f"输出文件: {output_path}")
    log_info("=" * 60)

    # 采集三大数据源
    stats_data = fetch_stats_data()
    market_data = fetch_market_data()
    news_data = fetch_news_data()

    # 整合结果
    result = {
        "collect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "report_date": report_date,
        "stats": stats_data,
        "market": market_data,
        "news": news_data,
        "errors": ERRORS,
        "summary": {
            "stats_status": stats_data.get("status", "unknown"),
            "stats_releases": len(stats_data.get("latest_releases", [])),
            "market_status": market_data.get("status", "unknown"),
            "market_source": market_data.get("source", ""),
            "market_indices": len(market_data.get("indices", {})),
            "news_status": news_data.get("status", "unknown"),
            "news_count": len(news_data.get("top_news", [])),
            "total_errors": len(ERRORS),
        },
    }

    # 写入 JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log_info(f"数据已写入: {output_path}")
    except Exception as e:
        log_error(f"写入JSON失败: {str(e)}")
        # 输出到 stdout
        print(json.dumps(result, ensure_ascii=False, indent=2))

    # 打印摘要
    log_info("=" * 60)
    log_info("采集摘要:")
    log_info(f"  国家统计局: {stats_data.get('status')} - {len(stats_data.get('latest_releases', []))}条发布")
    log_info(f"  A股行情: {market_data.get('status')} - 数据源:{market_data.get('source', '无')} - {len(market_data.get('indices', {}))}个指数")
    log_info(f"  财经新闻: {news_data.get('status')} - {len(news_data.get('top_news', []))}条新闻")
    log_info(f"  错误数: {len(ERRORS)}")
    log_info("=" * 60)

    # 有错误时返回非0退出码
    if ERRORS:
        sys.exit(1)


if __name__ == "__main__":
    main()
