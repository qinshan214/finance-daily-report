#!/usr/bin/env python3
"""
AI优化日报脚本 - AI优先，脚本保底，自动降级
功能：
1. 读取基础日报和采集数据
2. 调用AI生成深度分析部分
3. 合并基础数据和AI分析
4. 失败时自动降级（返回None，使用纯脚本版）
5. 缓存机制，避免重复调用AI，减少额度消耗

减少AI额度消耗的优化：
- 只给AI数据摘要，不给完整数据
- 限制输出长度（最多2000字）
- 缓存当天结果，不重复调用
- 失败不重试，直接降级
"""

import os
import sys
import json
import time
import requests
from datetime import datetime

# ============================================================
# 配置
# ============================================================

# AI API配置（从环境变量读取）
AI_API_KEY = os.environ.get("DOUBAO_API_KEY", "")
AI_API_URL = os.environ.get("DOUBAO_API_URL", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
AI_MODEL = os.environ.get("DOUBAO_MODEL", "doubao-seed-1-6-250615")

# 输出限制
MAX_OUTPUT_TOKENS = 1500  # 限制AI输出长度，减少token消耗
AI_TIMEOUT = 30  # AI调用超时时间

# 缓存目录
CACHE_DIR = "output/ai_cache"


def log(level, message):
    """日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def load_json(filepath):
    """加载JSON文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log("ERROR", f"加载JSON失败: {filepath}, 错误: {e}")
        return None


def load_markdown(filepath):
    """加载Markdown文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        log("ERROR", f"加载Markdown失败: {filepath}, 错误: {e}")
        return None


def get_data_summary(data):
    """
    从采集数据中提取精简摘要，减少AI输入token
    只保留关键数据，不传递完整数据
    """
    summary = {
        "market": {},
        "sectors": {"top_gainers": [], "top_losers": []},
        "global": [],
        "news": [],
        "stats": []
    }

    # A股行情摘要（只保留指数名称、点位、涨跌幅）
    if data and "market" in data:
        indices = data["market"].get("indices", {})
        if isinstance(indices, dict):
            for name, idx in list(indices.items())[:5]:
                summary["market"][name] = {
                    "price": idx.get("current"),
                    "change_pct": idx.get("change_pct")
                }

    # 板块摘要（只保留前5个领涨/领跌）
    if data and "sectors" in data:
        for s in data["sectors"].get("top_gainers", [])[:5]:
            summary["sectors"]["top_gainers"].append({
                "name": s.get("name"),
                "change_pct": s.get("change_pct")
            })
        for s in data["sectors"].get("top_losers", [])[:5]:
            summary["sectors"]["top_losers"].append({
                "name": s.get("name"),
                "change_pct": s.get("change_pct")
            })

    # 全球市场摘要
    if data and "global_market" in data:
        markets = data["global_market"].get("markets", [])
        if isinstance(markets, dict):
            markets = list(markets.values())
        for m in markets[:5]:
            if isinstance(m, dict):
                summary["global"].append({
                    "name": m.get("name"),
                    "price": m.get("current"),
                    "change_pct": m.get("change_pct")
                })

    # 新闻摘要（只保留前8条标题）
    if data and "news" in data:
        for n in data["news"].get("top_news", [])[:8]:
            if isinstance(n, dict):
                summary["news"].append(n.get("title", ""))

    # 国家统计局摘要（只保留前5条标题）
    if data and "stats" in data:
        for r in data["stats"].get("latest_releases", [])[:5]:
            if isinstance(r, dict):
                summary["stats"].append(r.get("title", ""))

    return summary


def build_prompt(data_summary):
    """
    构建精简的prompt，减少输入token
    要求AI生成简洁的深度分析，限制输出长度
    """
    prompt = f"""你是一位专业的财经分析师。请根据以下今日市场数据，生成简洁的深度分析。

【要求】
1. 总字数控制在1500字以内
2. 结构清晰，使用Markdown格式
3. 只分析，不罗列数据（数据已在基础部分展示）
4. 重点分析：市场趋势、板块轮动逻辑、新闻影响、投资建议
5. 投资建议仅供参考，需提示风险

【今日市场数据摘要】
{json.dumps(data_summary, ensure_ascii=False, indent=2)}

【输出结构】
## 🧠 深度分析（AI生成）
### 一、市场总览
（2-3句话概括今日市场特征和核心逻辑）

### 二、板块轮动分析
（分析领涨/领跌板块的原因和后续趋势）

### 三、重点新闻解读
（选取2-3条重要新闻，分析对市场的影响）

### 四、投资策略建议
（短期/中期策略，1-2条即可，需提示风险）

请直接输出Markdown内容，不要有其他解释。"""

    return prompt


def call_ai_api(prompt):
    """
    调用AI API生成深度分析
    失败时返回None，触发降级
    """
    if not AI_API_KEY:
        log("ERROR", "未设置 DOUBAO_API_KEY 环境变量，AI优化跳过")
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_API_KEY}"
    }

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0.7
    }

    try:
        log("INFO", f"正在调用AI API（模型: {AI_MODEL}，最大输出: {MAX_OUTPUT_TOKENS} tokens）...")
        start_time = time.time()

        # 禁用代理，避免本地代理环境导致连接失败
        no_proxy = {"http": None, "https": None}
        resp = requests.post(AI_API_URL, headers=headers, json=payload, timeout=AI_TIMEOUT, proxies=no_proxy)
        elapsed = time.time() - start_time

        if resp.status_code == 200:
            data = resp.json()
            ai_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})

            log("INFO", f"AI调用成功，耗时: {elapsed:.1f}秒，"
                        f"输入tokens: {usage.get('prompt_tokens', '?')}，"
                        f"输出tokens: {usage.get('completion_tokens', '?')}，"
                        f"总tokens: {usage.get('total_tokens', '?')}")

            if ai_content and len(ai_content) > 100:
                return ai_content
            else:
                log("ERROR", f"AI返回内容过短（{len(ai_content)}字符），视为失败")
                return None
        else:
            log("ERROR", f"AI API调用失败，状态码: {resp.status_code}，响应: {resp.text[:200]}")
            return None

    except requests.exceptions.Timeout:
        log("ERROR", f"AI API调用超时（{AI_TIMEOUT}秒）")
        return None
    except Exception as e:
        log("ERROR", f"AI API调用异常: {str(e)}")
        return None


def check_cache(date_str):
    """
    检查当天是否已有AI缓存结果
    避免重复调用AI，减少额度消耗
    """
    cache_file = os.path.join(CACHE_DIR, f"ai_analysis_{date_str}.md")
    if os.path.exists(cache_file):
        log("INFO", f"发现当天AI缓存结果: {cache_file}，直接使用，不重复调用AI")
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            log("ERROR", f"读取缓存失败: {e}")
            return None
    return None


def save_cache(date_str, ai_content):
    """保存AI结果到缓存，供当天后续使用"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(CACHE_DIR, f"ai_analysis_{date_str}.md")
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(ai_content)
        log("INFO", f"AI结果已缓存: {cache_file}")
    except Exception as e:
        log("ERROR", f"保存缓存失败: {e}")


def merge_report(base_report, ai_content, date_str, ai_success):
    """
    合并基础日报和AI深度分析
    AI成功：基础数据 + AI分析
    AI失败：仅基础数据，并标注
    """
    if ai_success and ai_content:
        # AI成功：在基础日报末尾添加AI深度分析
        merged = base_report.rstrip() + "\n\n---\n\n" + ai_content + "\n"
        # 在标题处标注AI增强
        merged = merged.replace("# 财经日报", "# 财经日报（AI增强版）", 1)
        log("INFO", "AI增强版日报生成成功（基础数据 + AI深度分析）")
        return merged
    else:
        # AI失败：纯脚本版，标注AI不可用
        note = "\n\n---\n\n> ⚠️ 今日AI深度分析暂不可用（AI调用失败），以下为纯脚本生成的基础数据。\n"
        merged = base_report.rstrip() + note
        log("INFO", "AI调用失败，已降级为纯脚本版日报")
        return merged


def main():
    """主函数"""
    if len(sys.argv) < 4:
        print("用法: python3 ai_enhance_report.py --date <YYYY-MM-DD> --base-report <基础日报路径> --data <采集数据路径> --output <输出路径>")
        sys.exit(1)

    # 解析参数
    args = {}
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--date":
            args["date"] = sys.argv[i+1]
            i += 2
        elif sys.argv[i] == "--base-report":
            args["base_report"] = sys.argv[i+1]
            i += 2
        elif sys.argv[i] == "--data":
            args["data"] = sys.argv[i+1]
            i += 2
        elif sys.argv[i] == "--output":
            args["output"] = sys.argv[i+1]
            i += 2
        else:
            i += 1

    date_str = args.get("date", datetime.now().strftime("%Y-%m-%d"))
    base_report_path = args.get("base_report", "")
    data_path = args.get("data", "")
    output_path = args.get("output", "")

    log("INFO", "=" * 60)
    log("INFO", f"开始AI优化日报: {date_str}")
    log("INFO", "=" * 60)

    # 1. 加载基础日报
    base_report = load_markdown(base_report_path)
    if not base_report:
        log("ERROR", "无法加载基础日报，终止")
        sys.exit(1)

    # 2. 加载采集数据
    data = load_json(data_path)

    # 3. 检查缓存（减少AI额度消耗）
    ai_content = check_cache(date_str)
    ai_success = False

    if ai_content:
        # 使用缓存结果
        ai_success = True
        log("INFO", "使用缓存的AI结果，不消耗AI额度")
    else:
        # 4. 提取数据摘要（减少输入token）
        if data:
            data_summary = get_data_summary(data)
            log("INFO", f"数据摘要提取完成（精简后约{len(json.dumps(data_summary, ensure_ascii=False))}字符）")
        else:
            data_summary = {}
            log("WARN", "无采集数据，使用空摘要")

        # 5. 构建prompt
        prompt = build_prompt(data_summary)
        log("INFO", f"Prompt构建完成（约{len(prompt)}字符）")

        # 6. 调用AI API（失败不重试，直接降级）
        ai_content = call_ai_api(prompt)

        if ai_content:
            ai_success = True
            # 7. 保存缓存（供当天后续使用）
            save_cache(date_str, ai_content)
        else:
            ai_success = False
            log("WARN", "AI调用失败，将降级为纯脚本版")

    # 8. 合并日报
    final_report = merge_report(base_report, ai_content, date_str, ai_success)

    # 9. 保存输出
    try:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_report)
        log("INFO", f"最终日报已保存: {output_path}")
    except Exception as e:
        log("ERROR", f"保存输出失败: {e}")
        sys.exit(1)

    # 10. 输出结果状态（供工作流判断）
    result = {
        "success": True,
        "ai_enhanced": ai_success,
        "date": date_str,
        "output": output_path,
        "mode": "ai_enhanced" if ai_success else "script_only"
    }
    print(json.dumps(result, ensure_ascii=False))

    log("INFO", "=" * 60)
    log("INFO", f"AI优化完成，模式: {'AI增强版' if ai_success else '纯脚本版（降级）'}")
    log("INFO", "=" * 60)


if __name__ == "__main__":
    main()
