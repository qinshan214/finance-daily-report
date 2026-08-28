#!/usr/bin/env python3
"""
腾讯云函数入口 - 每日财经日报（AI增强版）
功能：
1. 采集财经数据
2. 生成基础日报
3. AI优化（AI优先，失败自动降级）
4. 创建飞书文档
5. 发送邮件通知

部署平台：腾讯云函数SCF
触发方式：定时触发（每天20:00）
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime

# 添加脚本目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

# ============================================================
# 配置（从环境变量读取）
# ============================================================

# 飞书配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_DOC_PERMISSION = os.environ.get("FEISHU_DOC_PERMISSION", "tenant_readable")
FEISHU_DOC_COLLABORATOR_ID = os.environ.get("FEISHU_DOC_COLLABORATOR_ID", "")
FEISHU_DOC_COLLABORATOR_TYPE = os.environ.get("FEISHU_DOC_COLLABORATOR_TYPE", "userid")
FEISHU_DOC_COLLABORATOR_PERM = os.environ.get("FEISHU_DOC_COLLABORATOR_PERM", "full_access")

# 邮件配置
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = os.environ.get("SMTP_PORT", "465")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_TO = os.environ.get("MAIL_TO", "")

# AI配置（可选，不配置则使用纯脚本版）
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY", "")
DOUBAO_API_URL = os.environ.get("DOUBAO_API_URL", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
DOUBAO_MODEL = os.environ.get("DOUBAO_MODEL", "")

# 工作目录
WORK_DIR = "/tmp"
OUTPUT_DIR = os.path.join(WORK_DIR, "output")


def log(level, message):
    """日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def run_command(cmd, env=None):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            cwd=os.path.dirname(__file__)
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        log("ERROR", f"命令超时: {cmd}")
        return False, "Timeout"
    except Exception as e:
        log("ERROR", f"命令执行异常: {e}")
        return False, str(e)


def main_handler(event, context):
    """
    云函数入口函数
    event: 触发事件（定时触发时为空）
    context: 函数上下文
    """
    start_time = time.time()
    log("INFO", "=" * 60)
    log("INFO", "每日财经日报云函数开始执行")
    log("INFO", "=" * 60)

    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 获取日期
    date_str = datetime.now().strftime("%Y-%m-%d")
    log("INFO", f"当前日期: {date_str}")

    # 检查配置
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        log("ERROR", "未配置飞书应用信息，请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET 环境变量")
        return {"success": False, "error": "Missing Feishu config"}

    if not MAIL_TO:
        log("WARN", "未配置收件人邮箱，邮件推送将跳过")

    # 构建环境变量
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), 'scripts')

    # ============================================================
    # 步骤1：数据采集
    # ============================================================
    log("INFO", "========== 步骤1：数据采集 ==========")
    data_file = os.path.join(OUTPUT_DIR, f"data_{date_str}.json")
    success, output = run_command(
        f"python3 scripts/collect_data.py --date {date_str} --output {data_file}",
        env=env
    )
    if not success:
        log("WARN", "数据采集失败，将继续执行（使用空数据）")
    else:
        log("INFO", "数据采集成功")

    # ============================================================
    # 步骤2：生成基础日报
    # ============================================================
    log("INFO", "========== 步骤2：生成基础日报 ==========")
    base_report_file = os.path.join(OUTPUT_DIR, f"report_base_{date_str}.md")
    success, output = run_command(
        f"python3 scripts/generate_report.py --data {data_file} --output {base_report_file}",
        env=env
    )
    if not success:
        log("ERROR", "基础日报生成失败")
        return {"success": False, "error": "Failed to generate base report"}
    else:
        log("INFO", "基础日报生成成功")

    # ============================================================
    # 步骤3：AI优化（AI优先，失败自动降级）
    # ============================================================
    final_report_file = os.path.join(OUTPUT_DIR, f"report_{date_str}.md")
    report_mode = "纯脚本版"

    if DOUBAO_API_KEY and DOUBAO_MODEL:
        log("INFO", "========== 步骤3：AI优化（AI优先，失败自动降级） ==========")
        ai_report_file = os.path.join(OUTPUT_DIR, f"report_ai_{date_str}.md")

        # 设置AI环境变量
        ai_env = env.copy()
        ai_env["DOUBAO_API_KEY"] = DOUBAO_API_KEY
        ai_env["DOUBAO_API_URL"] = DOUBAO_API_URL
        ai_env["DOUBAO_MODEL"] = DOUBAO_MODEL

        success, output = run_command(
            f"python3 scripts/ai_enhance_report.py "
            f"--date {date_str} "
            f"--base-report {base_report_file} "
            f"--data {data_file} "
            f"--output {ai_report_file}",
            env=ai_env
        )

        # 检查AI是否成功
        ai_success = False
        if success and os.path.exists(ai_report_file):
            # 检查输出中是否包含AI增强标记
            try:
                with open(ai_report_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "AI增强版" in content or "深度分析" in content:
                        ai_success = True
            except Exception as e:
                log("ERROR", f"读取AI报告失败: {e}")

        if ai_success:
            log("INFO", "✅ AI优化成功，使用AI增强版日报")
            import shutil
            shutil.copy(ai_report_file, final_report_file)
            report_mode = "AI增强版"
        else:
            log("WARN", "⚠️ AI优化失败，自动降级为纯脚本版")
            import shutil
            shutil.copy(base_report_file, final_report_file)
            report_mode = "纯脚本版（降级）"
    else:
        log("INFO", "========== 步骤3：未配置AI，使用纯脚本版 ==========")
        import shutil
        shutil.copy(base_report_file, final_report_file)
        report_mode = "纯脚本版"

    log("INFO", f"最终日报模式: {report_mode}")

    # ============================================================
    # 步骤4：创建飞书文档
    # ============================================================
    log("INFO", "========== 步骤4：创建飞书文档 ==========")
    doc_url = ""

    # 设置飞书环境变量
    feishu_env = env.copy()
    feishu_env["FEISHU_APP_ID"] = FEISHU_APP_ID
    feishu_env["FEISHU_APP_SECRET"] = FEISHU_APP_SECRET
    feishu_env["FEISHU_DOC_PERMISSION"] = FEISHU_DOC_PERMISSION
    feishu_env["FEISHU_DOC_COLLABORATOR_ID"] = FEISHU_DOC_COLLABORATOR_ID
    feishu_env["FEISHU_DOC_COLLABORATOR_TYPE"] = FEISHU_DOC_COLLABORATOR_TYPE
    feishu_env["FEISHU_DOC_COLLABORATOR_PERM"] = FEISHU_DOC_COLLABORATOR_PERM

    success, output = run_command(
        f"python3 scripts/create_feishu_doc.py "
        f"--title \"财经日报-{date_str}（{report_mode}）\" "
        f"--content-file {final_report_file}",
        env=feishu_env
    )

    if success:
        # 从输出中提取文档链接
        try:
            import re
            match = re.search(r'https://[^\s]+docx/[^\s]+', output)
            if match:
                doc_url = match.group(0)
                log("INFO", f"飞书文档创建成功: {doc_url}")
            else:
                log("WARN", "无法从输出中提取飞书文档链接")
        except Exception as e:
            log("ERROR", f"提取文档链接失败: {e}")
    else:
        log("ERROR", "飞书文档创建失败")

    # ============================================================
    # 步骤5：邮件推送
    # ============================================================
    log("INFO", "========== 步骤5：邮件推送 ==========")

    if MAIL_TO and SMTP_USER and SMTP_PASSWORD:
        # 设置邮件环境变量
        mail_env = env.copy()
        mail_env["SMTP_SERVER"] = SMTP_SERVER
        mail_env["SMTP_PORT"] = SMTP_PORT
        mail_env["SMTP_USER"] = SMTP_USER
        mail_env["SMTP_PASSWORD"] = SMTP_PASSWORD

        success, output = run_command(
            f"python3 scripts/send_email.py "
            f"--to \"{MAIL_TO}\" "
            f"--date {date_str} "
            f"--doc-url \"{doc_url}\" "
            f"--attach {final_report_file}",
            env=mail_env
        )
        if success:
            log("INFO", "邮件发送成功")
        else:
            log("ERROR", "邮件发送失败")
    else:
        log("WARN", "未配置完整的邮件信息，跳过邮件推送")

    # ============================================================
    # 完成
    # ============================================================
    elapsed = time.time() - start_time
    log("INFO", "=" * 60)
    log("INFO", f"每日财经日报执行完成，耗时: {elapsed:.1f}秒")
    log("INFO", f"日报模式: {report_mode}")
    log("INFO", f"飞书文档: {doc_url}")
    log("INFO", "=" * 60)

    return {
        "success": True,
        "date": date_str,
        "mode": report_mode,
        "doc_url": doc_url,
        "elapsed_seconds": elapsed
    }


# 本地测试入口
if __name__ == "__main__":
    result = main_handler({}, {})
    print(json.dumps(result, ensure_ascii=False, indent=2))
