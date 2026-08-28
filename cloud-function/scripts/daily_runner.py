#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日财经日报统一入口脚本（自动化模式切换）
优先使用脚本模式执行，记录执行状态，支持降级通知。

功能：
1. 执行脚本模式（run_daily.py）
2. 记录执行状态到模式控制器
3. 执行失败时发送降级通知
4. 支持AI模式失败后的自动降级调用

使用方式：
    # 正常执行脚本模式
    python3 daily_runner.py --date 2026-08-28

    # AI模式失败后降级执行（会记录降级事件）
    python3 daily_runner.py --date 2026-08-28 --degraded-from ai --reason "AI API限流"

    # 仅测试执行，不发送邮件
    python3 daily_runner.py --date 2026-08-28 --no-email
"""
import json
import argparse
import os
import sys
import subprocess
import traceback
from datetime import datetime

# ============================================
# 配置
# ============================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(PROJECT_DIR, "logs")

# 导入模式控制器
sys.path.insert(0, SCRIPT_DIR)
from mode_controller import log_event, update_stats, recommend_mode, is_in_cooldown


def run_script_mode(date, no_email=False, no_feishu=False):
    """执行脚本模式"""
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "run_daily.py"), "--date", date]
    if no_email:
        cmd.append("--no-email")
    if no_feishu:
        cmd.append("--no-feishu")

    env = os.environ.copy()

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, env=env
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        return success, output
    except subprocess.TimeoutExpired:
        return False, "脚本执行超时（300秒）"
    except Exception as e:
        return False, f"脚本执行异常: {str(e)}\n{traceback.format_exc()}"


def send_degradation_notification(date, reason, output=""):
    """发送降级通知邮件"""
    try:
        # 构建降级通知内容
        subject = f"⚠️ 财经日报模式降级通知 - {date}"
        body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:sans-serif;line-height:1.6;color:#333;">
    <div style="background:#fff3cd;border:1px solid #ffeaa7;border-radius:8px;padding:20px;max-width:600px;margin:0 auto;">
        <h2 style="color:#856404;margin-top:0;">⚠️ 财经日报模式降级通知</h2>
        <p><strong>日期：</strong>{date}</p>
        <p><strong>降级原因：</strong>{reason}</p>
        <p><strong>当前模式：</strong>脚本模式（保底模式）</p>
        <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
        <p style="font-size:13px;color:#666;">
            脚本模式内容相对基础，如需更丰富的分析解读，请检查AI服务状态后手动触发AI模式。
        </p>
        <p style="font-size:12px;color:#999;margin-top:16px;">
            本邮件由财经日报自动化系统自动发送
        </p>
    </div>
</body>
</html>
"""

        # 调用send_email.py发送通知
        cmd = [
            sys.executable, os.path.join(SCRIPT_DIR, "send_email.py"),
            "--to", os.environ.get("SMTP_USER", ""),
            "--date", date,
            "--full-content", body,
            "--status", "warning",
        ]

        env = os.environ.copy()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        return result.returncode == 0
    except Exception as e:
        print(f"[WARN] 降级通知发送失败: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description='每日财经日报统一入口脚本（自动化模式切换）')
    parser.add_argument('--date', '-d', help='报告日期（YYYY-MM-DD，默认今天）')
    parser.add_argument('--no-email', action='store_true', help='不发送邮件')
    parser.add_argument('--no-feishu', action='store_true', help='不生成飞书文档')
    parser.add_argument('--degraded-from', choices=['ai', 'manual'],
                        help='降级来源（ai=AI模式失败降级，manual=手动降级）')
    parser.add_argument('--reason', help='降级原因')
    parser.add_argument('--notify', action='store_true', help='发送降级通知邮件')
    args = parser.parse_args()

    date = args.date or datetime.now().strftime('%Y-%m-%d')

    print("=" * 60)
    print(f"每日财经日报统一入口 - {date}")
    print("=" * 60)

    # 检查是否在降级冷却期
    in_cooldown, remaining = is_in_cooldown()
    if in_cooldown:
        print(f"[INFO] 当前在降级冷却期内（剩余{remaining:.0f}分钟），强制使用脚本模式")

    # 记录降级事件
    if args.degraded_from:
        reason = args.reason or f"从{args.degraded_from}模式降级"
        log_event("script", "degraded", date, reason, {"degraded_from": args.degraded_from})
        update_stats("script", "degraded")
        print(f"[INFO] 记录降级事件: {reason}")

        # 发送降级通知
        if args.notify:
            print("[INFO] 发送降级通知邮件...")
            send_degradation_notification(date, reason)

    # 执行脚本模式
    print(f"[INFO] 开始执行脚本模式...")
    print(f"[INFO] 邮件推送: {'关闭' if args.no_email else '开启'}")
    print(f"[INFO] 飞书文档: {'关闭' if args.no_feishu else '开启'}")
    print("-" * 60)

    success, output = run_script_mode(date, args.no_email, args.no_feishu)

    print("-" * 60)

    # 记录执行结果
    if success:
        print("[SUCCESS] 脚本模式执行成功")
        log_event("script", "success", date, "脚本模式执行成功")
        update_stats("script", "success")
    else:
        print("[ERROR] 脚本模式执行失败")
        print(f"[ERROR] 错误信息: {output[:500]}")
        log_event("script", "failed", date, f"脚本模式执行失败: {output[:200]}")
        update_stats("script", "failed")

    print("=" * 60)

    # 显示当前推荐模式
    rec = recommend_mode()
    mode_name = "AI模式" if rec["recommended_mode"] == "ai" else "脚本模式"
    print(f"[INFO] 当前推荐模式: {mode_name}")
    print(f"[INFO] 推荐理由: {rec['reason']}")
    print("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
