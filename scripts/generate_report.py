#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纯脚本日报生成器（增强版，AI降级模式）

读取 collect_data.py 输出的 JSON 数据，基于模板生成 Markdown 格式日报，
然后调用 send_email.py 发送邮件。完全不依赖 AI。

支持的数据模块：
- 国家统计局（最新发布+预告）
- A股行情（5大指数表格+市场简评）
- 行业板块（领涨领跌Top5）
- 全球市场（美股/黄金/原油/汇率）
- 财经新闻（4分类+Top新闻）

使用方式：
    python3 generate_report.py --data output/data.json [--output report.md] [--send-email]
"""

import json
import argparse
import os
import sys
import subprocess
from datetime import datetime


def load_data(data_path):
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_report(data):
    """基于 JSON 数据生成 Markdown 日报"""
    report_date = data.get('report_date', datetime.now().strftime('%Y-%m-%d'))
    collect_time = data.get('collect_time', '')
    elapsed = data.get('elapsed_seconds', 0)

    lines = []
    lines.append(f"# 财经日报-{report_date}")
    lines.append("")
    lines.append(f"> 本报告由自动化脚本生成（AI降级模式），数据来源于公开网站。")
    lines.append(f"> 采集时间：{collect_time} | 耗时：{elapsed}秒")
    lines.append("")

    # ===== 板块一：国家统计局 =====
    lines.append("## 板块一：国家统计局最新发布")
    lines.append("")
    stats = data.get('stats', {})
    releases = stats.get('latest_releases', [])

    if releases:
        lines.append("### 最新发布数据")
        lines.append("")
        for i, item in enumerate(releases[:10], 1):
            title = item.get('title', '无标题')
            date = item.get('date', '')
            url = item.get('url', '')
            date_str = f"（{date}）" if date else ""
            lines.append(f"{i}. **{title}**{date_str}")
            if url:
                lines.append(f"   [查看原文]({url})")
            lines.append("")
    else:
        lines.append("*当日无新发布数据*")
        lines.append("")

    upcoming = stats.get('upcoming', [])
    if upcoming:
        lines.append("### 近期发布预告")
        lines.append("")
        for item in upcoming[:8]:
            event = item.get('event', '')
            if event:
                lines.append(f"- {event}")
        lines.append("")

    # ===== 板块二：A股行情 =====
    lines.append("## 板块二：A股行情与资金流向")
    lines.append("")
    market = data.get('market', {})
    indices = market.get('indices', {})
    source = market.get('source', '未知')

    lines.append(f"*数据来源：{source}*")
    lines.append("")

    if indices:
        lines.append("### 2.1 主要指数表现")
        lines.append("")
        lines.append("| 指数 | 最新点位 | 涨跌额 | 涨跌幅 | 成交额 |")
        lines.append("|------|---------|--------|--------|--------|")

        for name, idx in indices.items():
            current = idx.get('current', 0)
            change = idx.get('change', 0)
            change_pct = idx.get('change_pct', 0)
            amount = idx.get('amount', 0)
            amount_yi = amount / 1e8 if amount else 0
            change_sign = "+" if change >= 0 else ""
            pct_sign = "+" if change_pct >= 0 else ""
            lines.append(f"| {name} | {current:.2f} | {change_sign}{change:.2f} | {pct_sign}{change_pct:.2f}% | {amount_yi:.1f}亿 |")

        lines.append("")

        # 市场简评
        lines.append("### 2.2 市场简评")
        lines.append("")
        up_count = sum(1 for idx in indices.values() if idx.get('change_pct', 0) > 0)
        total_count = len(indices)
        avg_pct = sum(idx.get('change_pct', 0) for idx in indices.values()) / total_count if total_count else 0

        if avg_pct > 1:
            lines.append(f"今日A股全线大涨，{up_count}/{total_count}个指数上涨，平均涨幅{avg_pct:.2f}%。")
        elif avg_pct > 0:
            lines.append(f"今日A股震荡上行，{up_count}/{total_count}个指数上涨，平均涨幅{avg_pct:.2f}%。")
        elif avg_pct > -1:
            lines.append(f"今日A股小幅调整，{up_count}/{total_count}个指数上涨，平均跌幅{abs(avg_pct):.2f}%。")
        else:
            lines.append(f"今日A股大幅下跌，{up_count}/{total_count}个指数上涨，平均跌幅{abs(avg_pct):.2f}%。")

        sorted_indices = sorted(indices.items(), key=lambda x: x[1].get('change_pct', 0), reverse=True)
        if sorted_indices:
            leader = sorted_indices[0]
            laggard = sorted_indices[-1]
            lines.append(f"- 领涨指数：**{leader[0]}**（{leader[1].get('change_pct', 0):+.2f}%）")
            lines.append(f"- 领跌指数：**{laggard[0]}**（{laggard[1].get('change_pct', 0):+.2f}%）")
        lines.append("")

    # 行业板块
    sectors = data.get('sectors', {})
    if sectors.get('sectors'):
        lines.append("### 2.3 行业板块变化")
        lines.append("")
        top_gainers = sectors.get('top_gainers', [])
        top_losers = sectors.get('top_losers', [])

        if top_gainers:
            lines.append("**领涨板块 Top5：**")
            lines.append("")
            lines.append("| 排名 | 板块 | 涨跌幅 | 领涨股 | 领涨股涨幅 |")
            lines.append("|------|------|--------|--------|-----------|")
            for i, s in enumerate(top_gainers[:5], 1):
                name = s.get('name', '')
                pct = s.get('change_pct', 0)
                leader = s.get('leader_stock', '')
                leader_pct = s.get('leader_change', 0)
                lines.append(f"| {i} | {name} | {pct:+.2f}% | {leader} | {leader_pct:+.2f}% |")
            lines.append("")

        if top_losers:
            lines.append("**领跌板块 Top5：**")
            lines.append("")
            lines.append("| 排名 | 板块 | 涨跌幅 |")
            lines.append("|------|------|--------|")
            for i, s in enumerate(top_losers[:5], 1):
                name = s.get('name', '')
                pct = s.get('change_pct', 0)
                lines.append(f"| {i} | {name} | {pct:+.2f}% |")
            lines.append("")

    # 全球市场
    global_market = data.get('global_market', {})
    if global_market.get('markets'):
        lines.append("### 2.4 全球市场动态")
        lines.append("")
        lines.append("| 指标 | 最新价 | 涨跌额 | 涨跌幅 |")
        lines.append("|------|--------|--------|--------|")
        for name, m in global_market['markets'].items():
            price = m.get('price', 0)
            change = m.get('change', 0)
            change_pct = m.get('change_pct', 0)
            change_sign = "+" if change >= 0 else ""
            pct_sign = "+" if change_pct >= 0 else ""
            lines.append(f"| {name} | {price} | {change_sign}{change} | {pct_sign}{change_pct}% |")
        lines.append("")
    elif global_market.get('status') == 'failed':
        lines.append("### 2.4 全球市场动态")
        lines.append("")
        lines.append("*全球市场数据采集失败*")
        lines.append("")

    # ===== 板块三：财经新闻 =====
    lines.append("## 板块三：当日重要财经新闻")
    lines.append("")
    news = data.get('news', {})
    categories = news.get('categories', {})

    category_names = [
        ("international", "3.1 国际局势"),
        ("macro", "3.2 宏观政策"),
        ("company", "3.3 公司动态"),
        ("other", "3.4 其他新闻"),
    ]

    for cat_key, cat_title in category_names:
        items = categories.get(cat_key, [])
        if items:
            lines.append(f"### {cat_title}")
            lines.append("")
            for item in items[:8]:
                title = item.get('title', '')
                url = item.get('url', '')
                if title:
                    lines.append(f"- [{title}]({url})" if url else f"- {title}")
            lines.append("")

    # ===== 板块四：数据采集说明 =====
    lines.append("## 板块四：数据采集说明")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("|------|------|")
    lines.append(f"| 采集时间 | {collect_time} |")
    lines.append(f"| 报告日期 | {report_date} |")
    lines.append(f"| 采集耗时 | {elapsed}秒 |")

    summary = data.get('summary', {})
    lines.append(f"| 国家统计局 | {summary.get('stats_status', '未知')} - {summary.get('stats_releases', 0)}条发布 |")
    lines.append(f"| A股行情 | {summary.get('market_status', '未知')} - {summary.get('market_source', '')} - {summary.get('market_indices', 0)}个指数 |")
    lines.append(f"| 行业板块 | {summary.get('sector_status', '未知')} - {summary.get('sector_count', 0)}个板块 |")
    lines.append(f"| 全球市场 | {summary.get('global_status', '未知')} - {summary.get('global_count', 0)}个指标 |")
    lines.append(f"| 财经新闻 | {summary.get('news_status', '未知')} - {summary.get('news_count', 0)}条新闻 |")

    errors = data.get('errors', [])
    if errors:
        lines.append(f"| 错误数 | {len(errors)} |")
        lines.append("")
        lines.append("**错误详情：**")
        for err in errors[:5]:
            lines.append(f"- {err[:100]}")
    else:
        lines.append("| 错误数 | 0 |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*本报告由纯脚本自动生成（AI降级模式），不含AI分析和解读。*")
    lines.append(f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    return "\n".join(lines)


def send_email(report_content, report_date, email_script_path):
    """调用 send_email.py 发送邮件（降级模式）"""
    cmd = [
        sys.executable, email_script_path,
        "--to", "161626837@qq.com",
        "--date", report_date,
        "--full-content", report_content,
    ]
    env = os.environ.copy()
    env["SMTP_USER"] = "161626837@qq.com"
    env["SMTP_PASSWORD"] = "noqadiemaigkbifj"

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"邮件发送失败: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description='纯脚本日报生成器（增强版，AI降级模式）')
    parser.add_argument('--data', '-d', required=True, help='collect_data.py 输出的 JSON 文件路径')
    parser.add_argument('--output', '-o', help='输出 Markdown 文件路径')
    parser.add_argument('--send-email', action='store_true', help='生成后自动发送邮件')
    parser.add_argument('--email-script', default='scripts/send_email.py', help='邮件脚本路径')
    args = parser.parse_args()

    print(f"加载数据: {args.data}")
    data = load_data(args.data)
    report_date = data.get('report_date', datetime.now().strftime('%Y-%m-%d'))

    print("生成日报...")
    report = generate_report(data)

    output_path = args.output or f"output/report_{report_date}.md"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"日报已生成: {output_path}")

    if args.send_email:
        print("发送邮件...")
        success = send_email(report, report_date, args.email_script)
        if success:
            print("邮件发送成功！")
        else:
            print("邮件发送失败！", file=sys.stderr)
            sys.exit(1)

    print("完成！")


if __name__ == "__main__":
    main()
