#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模式控制器（自动化模式切换）
负责检测AI服务健康状态、选择运行模式、记录模式切换日志和统计。

模式说明：
- AI模式：通过AI助手执行，内容更丰富，有分析解读，但依赖AI服务
- 脚本模式：通过run_daily.py执行，稳定可靠，0 token消耗，内容相对基础

功能：
1. 记录AI服务健康状态（通过AI定时任务的执行结果）
2. 自动选择运行模式（AI优先，失败降级到脚本）
3. 记录模式切换日志和统计
4. 降级时发送通知邮件

使用方式：
    # 记录AI模式执行成功
    python3 mode_controller.py --mode ai --status success --date 2026-08-28

    # 记录AI模式执行失败，触发降级
    python3 mode_controller.py --mode ai --status failed --date 2026-08-28 --reason "API限流"

    # 查询当前推荐模式
    python3 mode_controller.py --query

    # 查看模式切换统计
    python3 mode_controller.py --stats
"""
import json
import argparse
import os
import sys
from datetime import datetime, timedelta

# ============================================
# 配置
# ============================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
MODE_LOG_FILE = os.path.join(LOG_DIR, "mode_switch_log.json")
MODE_STATS_FILE = os.path.join(LOG_DIR, "mode_stats.json")

# 降级阈值配置
DEGRADE_THRESHOLD = {
    "consecutive_failures": 2,      # 连续失败N次触发降级
    "daily_failure_rate": 0.3,      # 日失败率超过30%触发降级
    "cooldown_minutes": 60,         # 降级后冷却时间（分钟），冷却期内强制使用脚本模式
}


# ============================================
# 工具函数
# ============================================
def ensure_dir():
    """确保日志目录存在"""
    os.makedirs(LOG_DIR, exist_ok=True)


def load_json(filepath, default=None):
    """加载JSON文件"""
    if default is None:
        default = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(filepath, data):
    """保存JSON文件"""
    ensure_dir()
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_event(mode, status, date, reason="", details=None):
    """记录模式切换事件"""
    ensure_dir()
    log_data = load_json(MODE_LOG_FILE, {"events": []})

    event = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "mode": mode,           # ai / script
        "status": status,       # success / failed / degraded / fallback
        "reason": reason,
        "details": details or {},
    }
    log_data["events"].append(event)

    # 只保留最近90天的日志
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    log_data["events"] = [e for e in log_data["events"] if e.get("date", "") >= cutoff]

    save_json(MODE_LOG_FILE, log_data)
    return event


def get_consecutive_failures(mode="ai"):
    """获取连续失败次数"""
    log_data = load_json(MODE_LOG_FILE, {"events": []})
    events = log_data.get("events", [])

    # 按时间倒序排列
    sorted_events = sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True)

    count = 0
    for event in sorted_events:
        if event.get("mode") == mode:
            if event.get("status") == "failed":
                count += 1
            elif event.get("status") == "success":
                break
    return count


def get_daily_failure_rate(mode="ai", date=None):
    """获取当日失败率"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    log_data = load_json(MODE_LOG_FILE, {"events": []})
    events = [e for e in log_data.get("events", []) if e.get("date") == date and e.get("mode") == mode]

    if not events:
        return 0.0, 0, 0

    total = len(events)
    failures = sum(1 for e in events if e.get("status") == "failed")
    rate = failures / total if total > 0 else 0.0
    return rate, failures, total


def is_in_cooldown():
    """检查是否在降级冷却期内"""
    log_data = load_json(MODE_LOG_FILE, {"events": []})
    events = log_data.get("events", [])

    # 找到最近一次降级事件
    degrade_events = [e for e in events if e.get("status") in ["degraded", "fallback"]]
    if not degrade_events:
        return False, None

    latest = max(degrade_events, key=lambda x: x.get("timestamp", ""))
    degrade_time = datetime.strptime(latest["timestamp"], "%Y-%m-%d %H:%M:%S")
    elapsed = (datetime.now() - degrade_time).total_seconds() / 60

    if elapsed < DEGRADE_THRESHOLD["cooldown_minutes"]:
        remaining = DEGRADE_THRESHOLD["cooldown_minutes"] - elapsed
        return True, remaining
    return False, None


def recommend_mode():
    """推荐运行模式"""
    # 检查是否在冷却期
    in_cooldown, remaining = is_in_cooldown()
    if in_cooldown:
        return {
            "recommended_mode": "script",
            "reason": f"降级冷却期内（剩余{remaining:.0f}分钟），强制使用脚本模式",
            "confidence": "high",
        }

    # 检查连续失败次数
    consecutive = get_consecutive_failures("ai")
    if consecutive >= DEGRADE_THRESHOLD["consecutive_failures"]:
        return {
            "recommended_mode": "script",
            "reason": f"AI模式连续失败{consecutive}次，建议降级到脚本模式",
            "confidence": "high",
            "consecutive_failures": consecutive,
        }

    # 检查当日失败率
    rate, failures, total = get_daily_failure_rate("ai")
    if total >= 3 and rate > DEGRADE_THRESHOLD["daily_failure_rate"]:
        return {
            "recommended_mode": "script",
            "reason": f"AI模式当日失败率{rate:.0%}（{failures}/{total}），建议降级到脚本模式",
            "confidence": "medium",
            "failure_rate": rate,
        }

    # 默认推荐AI模式
    return {
        "recommended_mode": "ai",
        "reason": "AI服务状态正常，推荐使用AI模式",
        "confidence": "high",
        "consecutive_failures": consecutive,
    }


def update_stats(mode, status):
    """更新模式统计"""
    stats = load_json(MODE_STATS_FILE, {
        "ai": {"success": 0, "failed": 0, "total": 0},
        "script": {"success": 0, "failed": 0, "total": 0},
        "degradations": 0,
        "last_updated": "",
    })

    if mode in stats:
        stats[mode]["total"] += 1
        if status == "success":
            stats[mode]["success"] += 1
        else:
            stats[mode]["failed"] += 1

    if status in ["degraded", "fallback"]:
        stats["degradations"] += 1

    stats["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json(MODE_STATS_FILE, stats)
    return stats


def print_stats():
    """打印模式统计"""
    stats = load_json(MODE_STATS_FILE)
    if not stats:
        print("暂无统计数据")
        return

    print("=" * 50)
    print("模式切换统计")
    print("=" * 50)
    print(f"最后更新: {stats.get('last_updated', '未知')}")
    print()

    for mode in ["ai", "script"]:
        s = stats.get(mode, {})
        total = s.get("total", 0)
        success = s.get("success", 0)
        failed = s.get("failed", 0)
        rate = (success / total * 100) if total > 0 else 0
        mode_name = "AI模式" if mode == "ai" else "脚本模式"
        print(f"{mode_name}:")
        print(f"  总执行: {total}次")
        print(f"  成功: {success}次")
        print(f"  失败: {failed}次")
        print(f"  成功率: {rate:.1f}%")
        print()

    print(f"降级次数: {stats.get('degradations', 0)}次")
    print("=" * 50)


def print_recommendation():
    """打印推荐模式"""
    rec = recommend_mode()
    print("=" * 50)
    print("模式推荐")
    print("=" * 50)
    mode_name = "AI模式" if rec["recommended_mode"] == "ai" else "脚本模式"
    print(f"推荐模式: {mode_name}")
    print(f"推荐理由: {rec['reason']}")
    print(f"置信度: {rec['confidence']}")
    if "consecutive_failures" in rec:
        print(f"连续失败: {rec['consecutive_failures']}次")
    print("=" * 50)


# ============================================
# 主函数
# ============================================
def reset_stats():
    """重置模式统计数据"""
    default_stats = {
        "ai": {"success": 0, "failed": 0, "total": 0},
        "script": {"success": 0, "failed": 0, "total": 0},
        "degradations": 0,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_json(MODE_STATS_FILE, default_stats)

    # 同时清空模式切换日志
    save_json(MODE_LOG_FILE, {"events": []})

    print("✅ 模式统计数据已重置")
    print("   - 模式统计已清零")
    print("   - 模式切换日志已清空")
    print("   - 连续失败次数已重置")


def main():
    parser = argparse.ArgumentParser(description='模式控制器（自动化模式切换）')
    parser.add_argument('--mode', choices=['ai', 'script'], help='运行模式')
    parser.add_argument('--status', choices=['success', 'failed', 'degraded', 'fallback'],
                        help='执行状态')
    parser.add_argument('--date', help='报告日期（YYYY-MM-DD）')
    parser.add_argument('--reason', help='失败/降级原因')
    parser.add_argument('--query', action='store_true', help='查询当前推荐模式')
    parser.add_argument('--stats', action='store_true', help='查看模式切换统计')
    parser.add_argument('--reset', action='store_true', help='重置模式统计数据（生产环境部署时使用）')
    args = parser.parse_args()

    # 重置统计
    if args.reset:
        reset_stats()
        return

    # 查询模式
    if args.query:
        print_recommendation()
        return

    # 查看统计
    if args.stats:
        print_stats()
        return

    # 记录事件
    if args.mode and args.status:
        date = args.date or datetime.now().strftime("%Y-%m-%d")
        event = log_event(args.mode, args.status, date, args.reason)
        stats = update_stats(args.mode, args.status)
        print(f"已记录事件: {args.mode} / {args.status} / {date}")
        if args.reason:
            print(f"原因: {args.reason}")

        # 如果是失败，检查是否需要降级
        if args.status == "failed" and args.mode == "ai":
            consecutive = get_consecutive_failures("ai")
            if consecutive >= DEGRADE_THRESHOLD["consecutive_failures"]:
                print(f"\n⚠️ 警告：AI模式连续失败{consecutive}次，建议降级到脚本模式！")
                print(f"   冷却时间：{DEGRADE_THRESHOLD['cooldown_minutes']}分钟")
        return

    # 默认显示推荐
    print_recommendation()


if __name__ == "__main__":
    main()
