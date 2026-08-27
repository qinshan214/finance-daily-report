#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
失败告警脚本
当每日财经日报执行失败时，发送告警邮件通知用户。

功能：
1. 发送失败告警邮件（包含错误信息、执行时间、建议操作）
2. 支持连续失败计数和告警级别
3. 支持备用邮箱（如果配置）
4. 简洁的告警信息，不依赖日报内容

使用方式：
    python3 alert.py --date YYYY-MM-DD --error "错误信息" --level warning
    python3 alert.py --date YYYY-MM-DD --error-file error.log --level critical

告警级别：
- info: 普通通知（如部分模块失败但整体成功）
- warning: 警告（如日报生成失败但邮件发送成功）
- critical: 严重（如邮件发送失败，完全失联）
"""
import argparse
import os
import sys
import json
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime

# ============================================
# 配置
# ============================================
DEFAULT_SMTP_SERVER = "smtp.qq.com"
DEFAULT_SMTP_PORT = 465

# 告警级别配置
ALERT_LEVELS = {
    "info": {"emoji": "ℹ️", "title": "通知", "color": "#3498db"},
    "warning": {"emoji": "⚠️", "title": "警告", "color": "#f39c12"},
    "critical": {"emoji": "🚨", "title": "严重告警", "color": "#e74c3c"},
}


def send_alert_email(to_email, subject, body, smtp_user=None, smtp_password=None,
                      smtp_server=DEFAULT_SMTP_SERVER, smtp_port=DEFAULT_SMTP_PORT):
    """发送告警邮件"""
    smtp_user = smtp_user or os.environ.get("SMTP_USER", "")
    smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        print("[ERROR] 未配置邮箱账号或授权码，无法发送告警邮件")
        return False

    msg = MIMEText(body, 'html', 'utf-8')
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15)
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_email], msg.as_string())
        server.quit()
        print(f"[INFO] 告警邮件发送成功: {to_email}")
        return True
    except Exception as e:
        print(f"[ERROR] 告警邮件发送失败: {str(e)}")
        return False


def build_alert_body(date, error, level, consecutive_failures=0, status_file=None):
    """构建告警邮件HTML内容"""
    level_config = ALERT_LEVELS.get(level, ALERT_LEVELS["warning"])
    emoji = level_config["emoji"]
    title = level_config["title"]
    color = level_config["color"]

    # 读取最近执行状态
    recent_status = ""
    if status_file and os.path.exists(status_file):
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            sorted_dates = sorted(history.keys(), reverse=True)[:5]
            recent_status = "<h3>📊 最近执行记录</h3><ul>"
            for d in sorted_dates:
                s = history.get(d, {})
                st = s.get("status", "unknown")
                st_color = "#27ae60" if st == "success" else "#e74c3c" if st == "failed" else "#f39c12"
                recent_status += f'<li>{d}: <span style="color:{st_color}">{st}</span></li>'
            recent_status += "</ul>"
        except Exception:
            pass

    consecutive_html = ""
    if consecutive_failures > 0:
        consecutive_html = f"""
        <div style="background:#fff3cd;padding:10px;border-radius:5px;margin:10px 0;">
            <strong>连续失败次数：{consecutive_failures} 次</strong><br>
            建议检查数据源、网络连接、邮箱配置等。
        </div>
        """

    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .alert-header {{ background: {color}; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
            .alert-body {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px; }}
            .error-box {{ background: #fee; border-left: 4px solid #e74c3c; padding: 15px; margin: 15px 0; border-radius: 4px; }}
            .suggestion {{ background: #e8f5e9; border-left: 4px solid #27ae60; padding: 15px; margin: 15px 0; border-radius: 4px; }}
            code {{ background: #eee; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
        </style>
    </head>
    <body>
        <div class="alert-header">
            <h1 style="margin:0;font-size:24px;">{emoji} 财经日报 {title}</h1>
            <p style="margin:5px 0 0 0;opacity:0.9;">报告日期：{date}</p>
        </div>
        <div class="alert-body">
            <p><strong>告警时间：</strong>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

            {consecutive_html}

            <div class="error-box">
                <h3 style="margin-top:0;color:#e74c3c;">❌ 错误信息</h3>
                <pre style="white-space:pre-wrap;word-break:break-all;margin:0;">{error}</pre>
            </div>

            <div class="suggestion">
                <h3 style="margin-top:0;color:#27ae60;">💡 建议操作</h3>
                <ul>
                    <li>检查网络连接是否正常</li>
                    <li>检查数据源网站是否可访问</li>
                    <li>检查邮箱授权码是否过期</li>
                    <li>查看完整日志：<code>logs/run_{date}.log</code></li>
                    <li>手动执行测试：<code>python3 scripts/run_daily.py --date {date}</code></li>
                </ul>
            </div>

            {recent_status}

            <hr style="border:none;border-top:1px solid #ddd;margin:20px 0;">
            <p style="color:#999;font-size:12px;text-align:center;">
                此邮件由财经日报自动告警系统发送<br>
                如需停止告警，请修改配置文件或关闭定时任务
            </p>
        </div>
    </body>
    </html>
    """
    return html


def main():
    parser = argparse.ArgumentParser(description='财经日报失败告警脚本')
    parser.add_argument('--date', '-d', required=True, help='报告日期（YYYY-MM-DD）')
    parser.add_argument('--error', '-e', help='错误信息')
    parser.add_argument('--error-file', help='从文件读取错误信息')
    parser.add_argument('--level', '-l', default='warning', choices=['info', 'warning', 'critical'],
                        help='告警级别（info/warning/critical，默认warning）')
    parser.add_argument('--to', help='接收告警的邮箱（默认使用SMTP_USER）')
    parser.add_argument('--consecutive', type=int, default=0, help='连续失败次数')
    parser.add_argument('--status-file', help='状态文件路径')
    args = parser.parse_args()

    # 读取错误信息
    error = args.error or ""
    if args.error_file and os.path.exists(args.error_file):
        with open(args.error_file, 'r', encoding='utf-8') as f:
            error = f.read()

    if not error:
        error = "未知错误（未提供错误信息）"

    # 构建告警邮件
    level_config = ALERT_LEVELS.get(args.level, ALERT_LEVELS["warning"])
    subject = f"{level_config['emoji']} 财经日报{level_config['title']} - {args.date}"

    body = build_alert_body(
        date=args.date,
        error=error,
        level=args.level,
        consecutive_failures=args.consecutive,
        status_file=args.status_file,
    )

    # 发送告警邮件
    to_email = args.to or os.environ.get("SMTP_USER", "")
    if not to_email:
        print("[ERROR] 未指定接收邮箱，且未配置SMTP_USER")
        sys.exit(1)

    success = send_alert_email(to_email, subject, body)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
