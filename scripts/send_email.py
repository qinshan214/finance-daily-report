#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日财经日报邮件推送脚本

使用 QQ 邮箱 SMTP 发送财经日报邮件，包含日报核心摘要和飞书文档链接。

使用方式：
    # 方式一：通过环境变量设置授权码（推荐）
    export SMTP_PASSWORD="你的QQ邮箱授权码"
    python3 send_email.py --to 收件人邮箱 --doc-url 飞书文档链接 --date 日期 \
        --summary-stats "国家统计局摘要" --summary-market "A股行情摘要" --summary-news "财经新闻摘要"

    # 方式二：通过命令行参数传入授权码
    python3 send_email.py --user 发件人邮箱 --password 授权码 --to 收件人邮箱 ...

环境变量：
    SMTP_HOST     SMTP 服务器地址（默认 smtp.qq.com）
    SMTP_PORT     SMTP 端口（默认 465）
    SMTP_USER     发件人邮箱
    SMTP_PASSWORD 发件人邮箱授权码（不是登录密码）
"""

import smtplib
import argparse
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime


def get_config(args):
    """获取邮件配置，优先使用命令行参数，其次使用环境变量"""
    config = {
        'host': args.host or os.environ.get('SMTP_HOST', 'smtp.qq.com'),
        'port': args.port or int(os.environ.get('SMTP_PORT', '465')),
        'user': args.user or os.environ.get('SMTP_USER', ''),
        'password': args.password or os.environ.get('SMTP_PASSWORD', ''),
        'to': args.to or '',
        'doc_url': args.doc_url or '',
        'date': args.date or datetime.now().strftime('%Y年%m月%d日'),
        'summary_stats': args.summary_stats or '（定时任务执行时自动填充）',
        'summary_market': args.summary_market or '（定时任务执行时自动填充）',
        'summary_new': args.summary_news or '（定时任务执行时自动填充）',
        'full_content': args.full_content or '',
    }

    if not config['user']:
        print("错误：缺少发件人邮箱，请通过 --user 或 SMTP_USER 环境变量设置")
        sys.exit(1)
    if not config['password']:
        print("错误：缺少邮箱授权码，请通过 --password 或 SMTP_PASSWORD 环境变量设置")
        sys.exit(1)
    if not config['to']:
        print("错误：缺少收件人邮箱，请通过 --to 参数设置")
        sys.exit(1)

    return config


def format_summary_items(text):
    """将摘要文本格式化为 HTML 列表项"""
    items = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if line:
            # 移除开头的列表符号
            for prefix in ['- ', '* ', '• ', '1. ', '2. ', '3. ', '4. ', '5. ']:
                if line.startswith(prefix):
                    line = line[len(prefix):]
                    break
            items.append(f"<li>{line}</li>")
    if not items:
        items.append("<li>暂无数据</li>")
    return '\n                '.join(items)


def markdown_to_html(text):
    """简单的 Markdown 转 HTML（支持标题、列表、粗体、换行）"""
    import re
    lines = text.strip().split('\n')
    html_lines = []
    in_list = False
    for line in lines:
        line = line.rstrip()
        # 标题
        if line.startswith('# '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h1>{line[2:]}</h1>')
        elif line.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('### '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h3>{line[4:]}</h3>')
        # 列表项
        elif line.startswith('- ') or line.startswith('* '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            content = line[2:]
            # 粗体
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            html_lines.append(f'<li>{content}</li>')
        # 空行
        elif line == '':
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<br>')
        # 普通段落
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content = line
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            html_lines.append(f'<p>{content}</p>')
    if in_list:
        html_lines.append('</ul>')
    return '\n'.join(html_lines)


def build_email_content(config):
    """构建邮件 HTML 内容"""
    date = config['date']

    # 降级模式：发送完整日报内容
    if config['full_content']:
        body_html = markdown_to_html(config['full_content'])
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 680px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
            color: white;
            padding: 24px;
            border-radius: 8px 8px 0 0;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .header .date {{
            margin-top: 8px;
            font-size: 14px;
            opacity: 0.9;
        }}
        .warning {{
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 6px;
            padding: 12px 16px;
            margin: 16px 0;
            color: #856404;
            font-size: 14px;
        }}
        .content {{
            background: #fff;
            border: 1px solid #e8e8e8;
            border-top: none;
            padding: 24px;
            border-radius: 0 0 8px 8px;
        }}
        .content h1 {{ font-size: 22px; color: #2c3e50; border-bottom: 2px solid #e74c3c; padding-bottom: 8px; }}
        .content h2 {{ font-size: 18px; color: #34495e; margin-top: 24px; }}
        .content h3 {{ font-size: 16px; color: #34495e; margin-top: 16px; }}
        .content ul {{ padding-left: 20px; }}
        .content li {{ margin-bottom: 6px; font-size: 14px; }}
        .content p {{ font-size: 14px; margin: 8px 0; }}
        .footer {{
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 24px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>每日财经日报（完整内容）</h1>
        <div class="date">{date}</div>
    </div>
    <div class="content">
        <div class="warning">
            ⚠️ 注意：飞书文档创建失败，此为降级模式发送的完整日报内容。
        </div>
        {body_html}
    </div>
    <div class="footer">
        本邮件由每日财经日报自动化系统自动发送（降级模式）<br>
        数据来源：国家统计局、同花顺、东方财富、新浪财经
    </div>
</body>
</html>"""
        return html

    # 正常模式：摘要 + 飞书文档链接
    doc_url = config['doc_url']

    stats_items = format_summary_items(config['summary_stats'])
    market_items = format_summary_items(config['summary_market'])
    news_items = format_summary_items(config['summary_new'])

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 680px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-radius: 8px 8px 0 0;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .header .date {{
            margin-top: 8px;
            font-size: 14px;
            opacity: 0.9;
        }}
        .content {{
            background: #fff;
            border: 1px solid #e8e8e8;
            border-top: none;
            padding: 24px;
            border-radius: 0 0 8px 8px;
        }}
        .section {{
            margin-bottom: 20px;
        }}
        .section h2 {{
            font-size: 16px;
            color: #667eea;
            border-left: 4px solid #667eea;
            padding-left: 12px;
            margin-bottom: 12px;
        }}
        .section ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .section li {{
            margin-bottom: 6px;
            font-size: 14px;
        }}
        .doc-link {{
            background: #f6f8fa;
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            padding: 16px;
            text-align: center;
            margin-top: 24px;
        }}
        .doc-link a {{
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
        }}
        .footer {{
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 24px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>每日财经日报</h1>
        <div class="date">{date}</div>
    </div>
    <div class="content">
        <div class="section">
            <h2>一、国家统计局</h2>
            <ul>
                {stats_items}
            </ul>
        </div>
        <div class="section">
            <h2>二、A股行情与资金流向</h2>
            <ul>
                {market_items}
            </ul>
        </div>
        <div class="section">
            <h2>三、重要财经新闻</h2>
            <ul>
                {news_items}
            </ul>
        </div>
        <div class="doc-link">
            <a href="{doc_url}" target="_blank">点击查看完整日报（飞书文档）</a>
        </div>
    </div>
    <div class="footer">
        本邮件由每日财经日报自动化系统自动发送<br>
        数据来源：国家统计局、同花顺、东方财富、新浪财经
    </div>
</body>
</html>"""
    return html


def send_email(config, html_content):
    """发送邮件"""
    msg = MIMEMultipart('alternative')
    msg['From'] = config['user']
    msg['To'] = config['to']
    msg['Subject'] = Header(f"财经日报-{config['date']}", 'utf-8')
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP_SSL(config['host'], config['port'])
        server.login(config['user'], config['password'])
        server.sendmail(config['user'], [config['to']], msg.as_string())
        server.quit()
        print(f"邮件发送成功！收件人：{config['to']}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("邮件发送失败：认证错误，请检查邮箱地址和授权码是否正确")
        return False
    except Exception as e:
        print(f"邮件发送失败：{str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description='每日财经日报邮件推送脚本')
    parser.add_argument('--host', help='SMTP 服务器地址（默认 smtp.qq.com）')
    parser.add_argument('--port', type=int, help='SMTP 端口（默认 465）')
    parser.add_argument('--user', help='发件人邮箱地址')
    parser.add_argument('--password', help='发件人邮箱授权码')
    parser.add_argument('--to', required=True, help='收件人邮箱地址')
    parser.add_argument('--doc-url', help='飞书文档链接')
    parser.add_argument('--date', help='日报日期（格式：YYYY年MM月DD日）')
    parser.add_argument('--summary-stats', help='国家统计局板块摘要（多行文本，每行一条）')
    parser.add_argument('--summary-market', help='A股行情板块摘要（多行文本，每行一条）')
    parser.add_argument('--summary-news', help='财经新闻板块摘要（多行文本，每行一条）')
    parser.add_argument('--full-content', help='完整日报Markdown内容（降级模式使用，飞书文档失败时发送完整内容）')

    args = parser.parse_args()
    config = get_config(args)
    html_content = build_email_content(config)
    success = send_email(config, html_content)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
