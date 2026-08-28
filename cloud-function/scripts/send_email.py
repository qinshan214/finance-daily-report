#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日财经日报邮件推送脚本（增强版）
使用 QQ 邮箱 SMTP 发送财经日报邮件，包含精美HTML模板、Markdown附件。

特性：
- 内联CSS样式，兼容各种邮件客户端（QQ/Gmail/Outlook）
- 支持Markdown表格转换
- 支持Markdown文件附件
- 响应式设计，适配移动端
- 两种模式：摘要模式（飞书链接）、完整内容模式

使用方式：
    # 摘要模式
    python3 send_email.py --to 收件人 --doc-url 飞书链接 --date 日期 \
        --summary-stats "..." --summary-market "..." --summary-news "..."

    # 完整内容模式 + 附件
    python3 send_email.py --to 收件人 --date 日期 --full-content "日报内容" --attach report.md

环境变量：
    SMTP_USER     发件人邮箱
    SMTP_PASSWORD 发件人邮箱授权码
"""
import smtplib
import argparse
import os
import sys
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from datetime import datetime


# ============================================
# 配置
# ============================================
DEFAULT_SMTP_HOST = "smtp.qq.com"
DEFAULT_SMTP_PORT = 465


# ============================================
# 工具函数
# ============================================
def get_config(args):
    """获取邮件配置"""
    config = {
        'host': args.host or os.environ.get('SMTP_HOST', DEFAULT_SMTP_HOST),
        'port': args.port or int(os.environ.get('SMTP_PORT', str(DEFAULT_SMTP_PORT))),
        'user': args.user or os.environ.get('SMTP_USER', ''),
        'password': args.password or os.environ.get('SMTP_PASSWORD', ''),
        'to': args.to or '',
        'doc_url': args.doc_url or '',
        'date': args.date or datetime.now().strftime('%Y年%m月%d日'),
        'summary_stats': args.summary_stats or '暂无数据',
        'summary_market': args.summary_market or '暂无数据',
        'summary_news': args.summary_news or '暂无数据',
        'full_content': args.full_content or '',
        'attach': args.attach or '',
        'status': args.status or 'success',
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


def inline_style(tag, style):
    """生成带内联样式的HTML标签"""
    return f'<{tag} style="{style}">'


def markdown_to_html(text):
    """增强版 Markdown 转 HTML（支持表格、标题、列表、粗体、代码、引用）"""
    lines = text.strip().split('\n')
    html_lines = []
    in_list = False
    in_table = False
    table_rows = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # 表格检测
        if '|' in line and i + 1 < len(lines) and re.match(r'^\s*\|?[\s\-:|]+\|?\s*$', lines[i+1]):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            # 解析表格
            table_rows = []
            # 表头
            headers = [c.strip() for c in line.strip('|').split('|')]
            table_rows.append(headers)
            i += 2  # 跳过分隔线
            # 表体
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                cells = [c.strip() for c in lines[i].strip('|').split('|')]
                table_rows.append(cells)
                i += 1
            # 生成表格HTML
            table_html = '<table style="width:100%;border-collapse:collapse;margin:12px 0;font-size:13px;">'
            # 表头
            table_html += '<tr style="background:#f8f9fa;">'
            for h in table_rows[0]:
                h = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', h)
                table_html += f'<th style="border:1px solid #dee2e6;padding:8px 12px;text-align:left;font-weight:600;color:#2c3e50;">{h}</th>'
            table_html += '</tr>'
            # 表体
            for row in table_rows[1:]:
                table_html += '<tr>'
                for cell in row:
                    cell = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', cell)
                    table_html += f'<td style="border:1px solid #dee2e6;padding:8px 12px;color:#495057;">{cell}</td>'
                table_html += '</tr>'
            table_html += '</table>'
            html_lines.append(table_html)
            continue

        # 标题
        if line.startswith('# '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[2:])
            html_lines.append(f'<h1 style="font-size:20px;color:#2c3e50;border-bottom:2px solid #e74c3c;padding-bottom:8px;margin:20px 0 12px;">{content}</h1>')
        elif line.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[3:])
            html_lines.append(f'<h2 style="font-size:17px;color:#34495e;margin:18px 0 10px;">{content}</h2>')
        elif line.startswith('### '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[4:])
            html_lines.append(f'<h3 style="font-size:15px;color:#34495e;margin:14px 0 8px;">{content}</h3>')
        # 引用
        elif line.startswith('> '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[2:])
            html_lines.append(f'<blockquote style="border-left:4px solid #3498db;background:#f8f9fa;padding:10px 16px;margin:10px 0;color:#555;font-size:13px;">{content}</blockquote>')
        # 列表项
        elif line.startswith('- ') or line.startswith('* '):
            if not in_list:
                html_lines.append('<ul style="padding-left:20px;margin:8px 0;">')
                in_list = True
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[2:])
            html_lines.append(f'<li style="margin-bottom:5px;font-size:14px;color:#444;">{content}</li>')
        # 有序列表
        elif re.match(r'^\d+\.\s', line):
            if not in_list:
                html_lines.append('<ol style="padding-left:20px;margin:8px 0;">')
                in_list = True
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', re.sub(r'^\d+\.\s', '', line))
            html_lines.append(f'<li style="margin-bottom:5px;font-size:14px;color:#444;">{content}</li>')
        # 空行
        elif line == '':
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<br>')
        # 分割线
        elif line.strip() in ['---', '***', '___']:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<hr style="border:none;border-top:1px solid #eee;margin:16px 0;">')
        # 普通段落
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content = line
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            # 链接
            content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color:#3498db;text-decoration:underline;">\1</a>', content)
            html_lines.append(f'<p style="font-size:14px;margin:8px 0;color:#444;line-height:1.7;">{content}</p>')

        i += 1

    if in_list:
        html_lines.append('</ul>')

    return '\n'.join(html_lines)


def format_summary_items(text):
    """将摘要文本格式化为 HTML 列表项"""
    items = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if line:
            for prefix in ['- ', '* ', '• ', '1. ', '2. ', '3. ', '4. ', '5. ']:
                if line.startswith(prefix):
                    line = line[len(prefix):]
                    break
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            items.append(f'<li style="margin-bottom:6px;font-size:14px;color:#444;">{line}</li>')
    if not items:
        items.append('<li style="font-size:14px;color:#999;">暂无数据</li>')
    return '\n'.join(items)


# ============================================
# 邮件HTML模板
# ============================================
def build_summary_email(config):
    """构建摘要模式邮件HTML（飞书链接模式）"""
    date = config['date']
    doc_url = config['doc_url']
    status = config.get('status', 'success')

    # 状态样式
    if status == 'success':
        status_color = '#27ae60'
        status_text = '✅ 执行成功'
    elif status == 'warning':
        status_color = '#f39c12'
        status_text = '⚠️ 部分成功'
    else:
        status_color = '#e74c3c'
        status_text = '❌ 执行失败'

    stats_items = format_summary_items(config['summary_stats'])
    market_items = format_summary_items(config['summary_market'])
    news_items = format_summary_items(config['summary_news'])

    # 飞书文档链接按钮
    doc_button = ''
    if doc_url:
        doc_button = f'''
        <table cellpadding="0" cellspacing="0" border="0" style="margin:20px auto;">
            <tr>
                <td align="center" style="border-radius:6px;background:#3498db;">
                    <a href="{doc_url}" target="_blank" style="display:inline-block;padding:12px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:6px;">
                        📄 查看完整飞书文档
                    </a>
                </td>
            </tr>
        </table>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f5f7fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f5f7fa;padding:20px 0;">
        <tr>
            <td align="center">
                <table cellpadding="0" cellspacing="0" border="0" width="640" style="max-width:640px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                    <!-- 头部Banner -->
                    <tr>
                        <td style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:28px 24px;text-align:center;">
                            <h1 style="margin:0;font-size:24px;color:#ffffff;font-weight:700;">📊 每日财经日报</h1>
                            <p style="margin:8px 0 0 0;font-size:14px;color:rgba(255,255,255,0.9);">{date}</p>
                            <p style="margin:6px 0 0 0;font-size:13px;color:{status_color};background:rgba(255,255,255,0.95);display:inline-block;padding:4px 12px;border-radius:12px;">{status_text}</p>
                        </td>
                    </tr>

                    <!-- 内容区域 -->
                    <tr>
                        <td style="padding:24px;">
                            <!-- 板块一：国家统计局 -->
                            <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom:20px;">
                                <tr>
                                    <td style="border-left:4px solid #e74c3c;padding-left:12px;">
                                        <h2 style="margin:0;font-size:16px;color:#2c3e50;font-weight:600;">🏛️ 国家统计局</h2>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding-top:10px;">
                                        <ul style="margin:0;padding-left:20px;">
                                            {stats_items}
                                        </ul>
                                    </td>
                                </tr>
                            </table>

                            <!-- 板块二：A股行情 -->
                            <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom:20px;">
                                <tr>
                                    <td style="border-left:4px solid #27ae60;padding-left:12px;">
                                        <h2 style="margin:0;font-size:16px;color:#2c3e50;font-weight:600;">📈 A股行情</h2>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding-top:10px;">
                                        <ul style="margin:0;padding-left:20px;">
                                            {market_items}
                                        </ul>
                                    </td>
                                </tr>
                            </table>

                            <!-- 板块三：重要新闻 -->
                            <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom:10px;">
                                <tr>
                                    <td style="border-left:4px solid #3498db;padding-left:12px;">
                                        <h2 style="margin:0;font-size:16px;color:#2c3e50;font-weight:600;">📰 重要新闻</h2>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding-top:10px;">
                                        <ul style="margin:0;padding-left:20px;">
                                            {news_items}
                                        </ul>
                                    </td>
                                </tr>
                            </table>

                            <!-- 飞书文档按钮 -->
                            {doc_button}
                        </td>
                    </tr>

                    <!-- 底部Footer -->
                    <tr>
                        <td style="background:#f8f9fa;padding:16px 24px;text-align:center;border-top:1px solid #eee;">
                            <p style="margin:0;font-size:12px;color:#999;line-height:1.6;">
                                本邮件由每日财经日报自动化系统自动发送<br>
                                数据来源：国家统计局、腾讯财经、新浪财经<br>
                                <span style="color:#bbb;">如需停止接收，请修改定时任务配置</span>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''
    return html


def build_full_email(config):
    """构建完整内容模式邮件HTML"""
    date = config['date']
    body_html = markdown_to_html(config['full_content'])

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f5f7fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f5f7fa;padding:20px 0;">
        <tr>
            <td align="center">
                <table cellpadding="0" cellspacing="0" border="0" width="680" style="max-width:680px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                    <!-- 头部Banner -->
                    <tr>
                        <td style="background:linear-gradient(135deg,#e74c3c 0%,#c0392b 100%);padding:24px;text-align:center;">
                            <h1 style="margin:0;font-size:22px;color:#ffffff;font-weight:700;">📊 每日财经日报（完整内容）</h1>
                            <p style="margin:8px 0 0 0;font-size:14px;color:rgba(255,255,255,0.9);">{date}</p>
                        </td>
                    </tr>

                    <!-- 提示信息 -->
                    <tr>
                        <td style="background:#fff3cd;padding:12px 24px;border-bottom:1px solid #ffeaa7;">
                            <p style="margin:0;font-size:13px;color:#856404;">⚠️ 注意：此为完整内容模式，飞书文档创建失败或未配置时使用。</p>
                        </td>
                    </tr>

                    <!-- 内容区域（支持横向滚动） -->
                    <tr>
                        <td style="padding:24px;overflow-x:auto;">
                            <div style="min-width:300px;">
                                {body_html}
                            </div>
                        </td>
                    </tr>

                    <!-- 底部Footer -->
                    <tr>
                        <td style="background:#f8f9fa;padding:16px 24px;text-align:center;border-top:1px solid #eee;">
                            <p style="margin:0;font-size:12px;color:#999;line-height:1.6;">
                                本邮件由每日财经日报自动化系统自动发送（完整内容模式）<br>
                                数据来源：国家统计局、腾讯财经、新浪财经
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''
    return html


# ============================================
# 邮件发送
# ============================================
def send_email(config):
    """发送邮件"""
    # 构建邮件
    msg = MIMEMultipart('alternative')
    msg['From'] = config['user']
    msg['To'] = config['to']
    msg['Subject'] = Header(f"📊 财经日报 - {config['date']}", 'utf-8')

    # 选择邮件模式
    if config['full_content']:
        html_content = build_full_email(config)
    else:
        html_content = build_summary_email(config)

    # 添加HTML内容
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    # 添加附件
    if config['attach'] and os.path.exists(config['attach']):
        try:
            with open(config['attach'], 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = os.path.basename(config['attach'])
            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            msg.attach(part)
            print(f"[INFO] 已添加附件: {filename}")
        except Exception as e:
            print(f"[WARN] 附件添加失败: {str(e)}")

    # 发送邮件
    try:
        server = smtplib.SMTP_SSL(config['host'], config['port'], timeout=30)
        server.login(config['user'], config['password'])
        server.sendmail(config['user'], [config['to']], msg.as_string())
        server.quit()
        print(f"[INFO] 邮件发送成功: {config['to']}")
        return True
    except Exception as e:
        print(f"[ERROR] 邮件发送失败: {str(e)}")
        return False


# ============================================
# 主函数
# ============================================
def main():
    parser = argparse.ArgumentParser(description='每日财经日报邮件推送脚本（增强版）')
    parser.add_argument('--host', help='SMTP服务器地址（默认smtp.qq.com）')
    parser.add_argument('--port', type=int, help='SMTP端口（默认465）')
    parser.add_argument('--user', help='发件人邮箱')
    parser.add_argument('--password', help='发件人邮箱授权码')
    parser.add_argument('--to', required=True, help='收件人邮箱')
    parser.add_argument('--date', help='日报日期（如2026年08月28日）')
    parser.add_argument('--doc-url', help='飞书文档链接（摘要模式）')
    parser.add_argument('--summary-stats', help='国家统计局摘要')
    parser.add_argument('--summary-market', help='A股行情摘要')
    parser.add_argument('--summary-news', help='重要新闻摘要')
    parser.add_argument('--full-content', help='完整日报内容（完整内容模式）')
    parser.add_argument('--attach', help='附件文件路径（如Markdown文件）')
    parser.add_argument('--status', choices=['success', 'warning', 'failed'], default='success',
                        help='执行状态（success/warning/failed）')
    args = parser.parse_args()

    config = get_config(args)
    success = send_email(config)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
