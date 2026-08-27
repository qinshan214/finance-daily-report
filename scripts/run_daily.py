#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日财经日报主控制脚本（纯脚本保底模式）

执行流程：
1. 调用 collect_data.py 采集数据
2. 调用 generate_report.py 生成基础版日报
3. 调用 send_email.py 发送邮件
4. 记录执行状态和日志

特点：
- 完全不依赖 AI，0 token 消耗
- 三级容错：数据采集失败→使用缓存→发送极简通知
- 完整执行日志和状态记录
- 支持配置文件

使用方式：
    python3 run_daily.py [--date YYYY-MM-DD] [--no-email] [--config config.json]

配置文件示例（config.json）：
{
    "email_to": "161626837@qq.com",
    "email_user": "161626837@qq.com",
    "email_password": "授权码",
    "output_dir": "output",
    "enable_email": true
}
"""

import json
import argparse
import os
import sys
import subprocess
import traceback
from datetime import datetime, timedelta


# ============================================
# 配置
# ============================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
DEFAULT_LOG_DIR = os.path.join(PROJECT_DIR, "logs")
STATUS_FILE = os.path.join(DEFAULT_LOG_DIR, "daily_status.json")

DEFAULT_CONFIG = {
    "email_to": "161626837@qq.com",
    "email_user": "161626837@qq.com",
    "email_password": "",  # 从环境变量或配置文件读取
    "output_dir": DEFAULT_OUTPUT_DIR,
    "log_dir": DEFAULT_LOG_DIR,
    "enable_email": True,
    "collect_script": os.path.join(SCRIPT_DIR, "collect_data.py"),
    "report_script": os.path.join(SCRIPT_DIR, "generate_report.py"),
    "email_script": os.path.join(SCRIPT_DIR, "send_email.py"),
}


# ============================================
# 工具函数
# ============================================
def log(level, message, log_file=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line, flush=True)
    if log_file:
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass


def run_script(script_path, args, timeout=120, env=None):
    """运行子脚本，返回 (success, stdout, stderr)"""
    cmd = [sys.executable, script_path] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, env=env or os.environ.copy()
        )
        success = result.returncode == 0
        return success, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"脚本执行超时（{timeout}秒）"
    except Exception as e:
        return False, "", f"脚本执行异常: {str(e)}"


def load_config(config_path):
    """加载配置文件"""
    config = DEFAULT_CONFIG.copy()
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            log("WARN", f"配置文件加载失败: {str(e)}")

    # 环境变量覆盖
    if os.environ.get("SMTP_PASSWORD"):
        config["email_password"] = os.environ["SMTP_PASSWORD"]
    if os.environ.get("SMTP_USER"):
        config["email_user"] = os.environ["SMTP_USER"]

    return config


def save_status(status, report_date):
    """保存执行状态"""
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        # 加载历史状态
        history = {}
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)

        history[report_date] = status
        # 只保留最近30天
        if len(history) > 30:
            sorted_dates = sorted(history.keys(), reverse=True)
            history = {d: history[d] for d in sorted_dates[:30]}

        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log("WARN", f"状态保存失败: {str(e)}")


# ============================================
# 主流程
# ============================================
def main():
    parser = argparse.ArgumentParser(description='每日财经日报主控制脚本（纯脚本保底模式）')
    parser.add_argument('--date', '-d', help='报告日期（YYYY-MM-DD，默认今天）')
    parser.add_argument('--config', '-c', help='配置文件路径')
    parser.add_argument('--no-email', action='store_true', help='不发送邮件（仅生成日报）')
    parser.add_argument('--output', '-o', help='输出目录')
    args = parser.parse_args()

    report_date = args.date or datetime.now().strftime('%Y-%m-%d')
    config = load_config(args.config)

    if args.no_email:
        config["enable_email"] = False
    if args.output:
        config["output_dir"] = args.output

    output_dir = config["output_dir"]
    log_dir = config.get("log_dir", DEFAULT_LOG_DIR)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"run_{report_date}.log")
    data_file = os.path.join(output_dir, f"data_{report_date}.json")
    report_file = os.path.join(output_dir, f"report_{report_date}.md")

    status = {
        "report_date": report_date,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "running",
        "steps": {},
        "errors": [],
    }

    log("INFO", "=" * 60, log_file)
    log("INFO", f"每日财经日报执行开始（纯脚本保底模式）", log_file)
    log("INFO", f"报告日期: {report_date}", log_file)
    log("INFO", f"输出目录: {output_dir}", log_file)
    log("INFO", f"邮件推送: {'开启' if config['enable_email'] else '关闭'}", log_file)
    log("INFO", "=" * 60, log_file)

    start_time = datetime.now()

    # ===== 第一步：采集数据 =====
    log("INFO", "【步骤1/3】开始采集数据...", log_file)
    collect_args = ["--output", data_file, "--date", report_date]
    success, stdout, stderr = run_script(
        config["collect_script"], collect_args, timeout=120
    )

    data_valid = False
    if os.path.exists(data_file):
        # 验证数据文件有效性
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                test_data = json.load(f)
                if test_data.get("summary"):
                    data_valid = True
                    success = True  # 数据文件有效，视为成功
        except Exception as e:
            log("ERROR", f"数据文件无效: {str(e)}", log_file)

    if success and data_valid:
        log("INFO", "数据采集成功", log_file)
        status["steps"]["collect"] = "success"
        # 打印采集摘要
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                summary = data.get("summary", {})
                log("INFO", f"  国家统计局: {summary.get('stats_releases', 0)}条发布", log_file)
                log("INFO", f"  A股行情: {summary.get('market_indices', 0)}个指数 ({summary.get('market_source', '')})", log_file)
                log("INFO", f"  行业板块: {summary.get('sector_count', 0)}个板块", log_file)
                log("INFO", f"  全球市场: {summary.get('global_count', 0)}个指标", log_file)
                log("INFO", f"  财经新闻: {summary.get('news_count', 0)}条新闻", log_file)
                log("INFO", f"  错误数: {summary.get('total_errors', 0)}", log_file)
        except Exception:
            pass
    else:
        log("ERROR", f"数据采集失败: {stderr[:200] if stderr else stdout[:200]}", log_file)
        status["steps"]["collect"] = "failed"
        status["errors"].append(f"数据采集失败: {stderr[:100]}")

        # 尝试使用昨天的缓存数据
        yesterday = (datetime.strptime(report_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        cache_file = os.path.join(output_dir, f"data_{yesterday}.json")
        if os.path.exists(cache_file):
            log("WARN", f"使用昨天({yesterday})的缓存数据", log_file)
            import shutil
            shutil.copy(cache_file, data_file)
            status["steps"]["collect"] = "using_cache"
            status["errors"].append(f"使用{yesterday}缓存数据")
        else:
            log("ERROR", "无缓存数据可用，终止执行", log_file)
            status["status"] = "failed"
            status["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_status(status, report_date)
            sys.exit(1)

    # ===== 第二步：生成日报 =====
    log("INFO", "【步骤2/3】开始生成日报...", log_file)
    report_args = ["--data", data_file, "--output", report_file]
    success, stdout, stderr = run_script(
        config["report_script"], report_args, timeout=60
    )

    if success and os.path.exists(report_file):
        log("INFO", f"日报生成成功: {report_file}", log_file)
        status["steps"]["report"] = "success"
    else:
        log("ERROR", f"日报生成失败: {stderr[:200]}", log_file)
        status["steps"]["report"] = "failed"
        status["errors"].append(f"日报生成失败: {stderr[:100]}")
        # 生成极简日报
        log("WARN", "生成极简日报作为兜底", log_file)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"# 财经日报-{report_date}\n\n")
            f.write(f"> 数据采集或日报生成出现异常，此为极简版日报。\n\n")
            f.write(f"## 数据文件\n\n{data_file}\n\n")
            f.write(f"## 错误信息\n\n{chr(10).join(status['errors'])}\n")
        status["steps"]["report"] = "minimal"

    # ===== 第三步：发送邮件 =====
    if config["enable_email"]:
        log("INFO", "【步骤3/3】开始发送邮件...", log_file)

        if not config.get("email_password"):
            log("ERROR", "未配置邮箱授权码（email_password），跳过邮件发送", log_file)
            status["steps"]["email"] = "skipped_no_password"
        else:
            # 读取日报内容
            with open(report_file, 'r', encoding='utf-8') as f:
                report_content = f.read()

            # 调用 send_email.py
            email_args = [
                "--to", config["email_to"],
                "--date", report_date,
                "--full-content", report_content,
            ]
            env = os.environ.copy()
            env["SMTP_USER"] = config["email_user"]
            env["SMTP_PASSWORD"] = config["email_password"]

            success, stdout, stderr = run_script(
                config["email_script"], email_args, timeout=30, env=env
            )

            if success:
                log("INFO", f"邮件发送成功: {config['email_to']}", log_file)
                status["steps"]["email"] = "success"
            else:
                log("ERROR", f"邮件发送失败: {stderr[:200] or stdout[:200]}", log_file)
                status["steps"]["email"] = "failed"
                status["errors"].append(f"邮件发送失败: {stderr[:100]}")
    else:
        log("INFO", "【步骤3/3】邮件推送已关闭，跳过", log_file)
        status["steps"]["email"] = "skipped"

    # ===== 完成 =====
    elapsed = (datetime.now() - start_time).total_seconds()
    status["status"] = "success" if not status["errors"] else "completed_with_errors"
    status["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status["elapsed_seconds"] = round(elapsed, 2)
    status["data_file"] = data_file
    status["report_file"] = report_file

    log("INFO", "=" * 60, log_file)
    log("INFO", "执行完成！", log_file)
    log("INFO", f"  状态: {status['status']}", log_file)
    log("INFO", f"  耗时: {elapsed:.2f}秒", log_file)
    log("INFO", f"  数据文件: {data_file}", log_file)
    log("INFO", f"  日报文件: {report_file}", log_file)
    if status["errors"]:
        log("WARN", f"  错误数: {len(status['errors'])}", log_file)
        for err in status["errors"]:
            log("WARN", f"    - {err[:80]}", log_file)
    log("INFO", "=" * 60, log_file)

    save_status(status, report_date)

    if status["status"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
