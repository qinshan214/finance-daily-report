#!/usr/bin/env python3
"""
AI增强完整版脚本（第二步）
功能：
1. 读取第一步脚本生成的JSON和Markdown
2. 调用AI生成深度分析（AI优先，失败自动降级）
3. 合并基础日报和AI分析
4. 创建飞书文档
5. 发送增强版邮件

使用方式：
    python3 ai_enhance_full.py --date 2026-08-28

前置条件：
    第一步必须先执行 run_daily.py --no-email --no-feishu
    生成 data_YYYY-MM-DD.json 和 report_YYYY-MM-DD.md
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime

# 添加脚本目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def log(level, message):
    """日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def run_command(cmd, env=None, timeout=120):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            cwd=os.path.dirname(SCRIPT_DIR)
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


def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description='AI增强完整版脚本（第二步）')
    parser.add_argument('--date', '-d', help='报告日期（YYYY-MM-DD，默认今天）')
    args = parser.parse_args()

    report_date = args.date or datetime.now().strftime('%Y-%m-%d')
    project_dir = os.path.dirname(SCRIPT_DIR)
    output_dir = os.path.join(project_dir, "output")

    log("INFO", "=" * 60)
    log("INFO", f"AI增强完整版开始执行: {report_date}")
    log("INFO", "=" * 60)

    # ============================================================
    # 检查第一步的输出文件
    # ============================================================
    log("INFO", "========== 检查第一步输出文件 ==========")
    data_file = os.path.join(output_dir, f"data_{report_date}.json")
    base_report_file = os.path.join(output_dir, f"report_{report_date}.md")

    if not os.path.exists(data_file):
        log("ERROR", f"数据文件不存在: {data_file}")
        log("ERROR", "请先执行第一步: python3 scripts/run_daily.py --no-email --no-feishu")
        return {"success": False, "error": "Missing data file"}

    if not os.path.exists(base_report_file):
        log("ERROR", f"基础日报文件不存在: {base_report_file}")
        log("ERROR", "请先执行第一步: python3 scripts/run_daily.py --no-email --no-feishu")
        return {"success": False, "error": "Missing base report file"}

    log("INFO", f"数据文件: {data_file}")
    log("INFO", f"基础日报: {base_report_file}")

    # ============================================================
    # 第二步：AI增强（AI优先，失败自动降级）
    # ============================================================
    log("INFO", "========== 第二步：AI增强（AI优先，失败自动降级） ==========")
    ai_report_file = os.path.join(output_dir, f"report_ai_{report_date}.md")
    final_report_file = os.path.join(output_dir, f"report_final_{report_date}.md")

    # 检查是否配置了AI API Key
    ai_api_key = os.environ.get("DOUBAO_API_KEY", "")
    ai_model = os.environ.get("DOUBAO_MODEL", "")

    if ai_api_key and ai_model:
        log("INFO", "检测到AI配置，尝试AI增强...")

        # 调用AI增强脚本
        success, output = run_command(
            f"python3 scripts/ai_enhance_report.py "
            f"--date {report_date} "
            f"--base-report {base_report_file} "
            f"--data {data_file} "
            f"--output {ai_report_file}",
            timeout=120
        )

        # 检查AI是否成功
        ai_success = False
        if success and os.path.exists(ai_report_file):
            try:
                with open(ai_report_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "AI增强版" in content or "深度分析" in content:
                        ai_success = True
            except Exception as e:
                log("ERROR", f"读取AI报告失败: {e}")

        if ai_success:
            log("INFO", "✅ AI增强成功，使用AI增强版日报")
            import shutil
            shutil.copy(ai_report_file, final_report_file)
            report_mode = "AI增强版"
        else:
            log("WARN", "⚠️ AI增强失败，自动降级为纯脚本版")
            import shutil
            shutil.copy(base_report_file, final_report_file)
            report_mode = "纯脚本版（降级）"
    else:
        log("WARN", "未配置AI API Key，使用纯脚本版")
        import shutil
        shutil.copy(base_report_file, final_report_file)
        report_mode = "纯脚本版"

    log("INFO", f"最终日报模式: {report_mode}")

    # ============================================================
    # 第三步：创建飞书文档
    # ============================================================
    log("INFO", "========== 第三步：创建飞书文档 ==========")
    feishu_app_id = os.environ.get("FEISHU_APP_ID", "")
    feishu_app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    doc_url = ""
    if feishu_app_id and feishu_app_secret:
        success, output = run_command(
            f"python3 scripts/create_feishu_doc.py "
            f"--title \"财经日报-{report_date}（{report_mode}）\" "
            f"--content-file {final_report_file}",
            timeout=60
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
    else:
        log("WARN", "未配置飞书应用信息，跳过飞书文档创建")

    # ============================================================
    # 第四步：发送增强版邮件
    # ============================================================
    log("INFO", "========== 第四步：发送增强版邮件 ==========")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    mail_to = os.environ.get("MAIL_TO", "")

    if mail_to and smtp_user and smtp_password:
        success, output = run_command(
            f"python3 scripts/send_email.py "
            f"--to \"{mail_to}\" "
            f"--date {report_date} "
            f"--doc-url \"{doc_url}\" "
            f"--attach {final_report_file}",
            timeout=60
        )
        if success:
            log("INFO", "增强版邮件发送成功")
        else:
            log("ERROR", "增强版邮件发送失败")
    else:
        log("WARN", "未配置完整的邮件信息，跳过邮件发送")

    # ============================================================
    # 完成
    # ============================================================
    log("INFO", "=" * 60)
    log("INFO", f"AI增强完整版执行完成")
    log("INFO", f"日报模式: {report_mode}")
    log("INFO", f"飞书文档: {doc_url}")
    log("INFO", f"最终日报: {final_report_file}")
    log("INFO", "=" * 60)

    return {
        "success": True,
        "date": report_date,
        "mode": report_mode,
        "doc_url": doc_url,
        "final_report": final_report_file
    }


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, ensure_ascii=False, indent=2))
