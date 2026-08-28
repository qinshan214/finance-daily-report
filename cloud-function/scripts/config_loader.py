#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一配置加载器
优先级：命令行参数 > 环境变量(.env) > config.json > 默认值

功能：
1. 自动加载.env文件
2. 自动加载config.json文件
3. 合并配置，按优先级覆盖
4. 配置校验，检查必要配置
5. 提供统一的配置访问接口

使用方式：
    from config_loader import load_config, validate_config

    # 加载配置
    config = load_config()

    # 访问配置
    smtp_user = config['email']['smtp_user']
    feishu_app_id = config['feishu']['app_id']

    # 校验配置
    errors = validate_config(config)
    if errors:
        print("配置错误:", errors)
"""
import os
import json
import sys
from typing import Dict, Any, List, Optional

# ============================================
# 配置
# ============================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# 默认配置
DEFAULT_CONFIG = {
    "email": {
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "smtp_user": "",
        "smtp_password": "",
        "email_to": "",
        "enable": True,
    },
    "feishu": {
        "app_id": "",
        "app_secret": "",
        "enable": True,
    },
    "script": {
        "output_dir": "output",
        "log_dir": "logs",
        "enable_alert": True,
    },
    "mode_switch": {
        "consecutive_failures": 2,
        "daily_failure_rate": 0.3,
        "cooldown_minutes": 60,
    },
    "data_collection": {
        "news_count": 50,
        "stock_ranking_count": 10,
        "request_timeout": 15,
        "request_retries": 2,
    },
}

# 环境变量映射（环境变量名 -> 配置路径）
ENV_MAPPING = {
    "SMTP_HOST": ("email", "smtp_host"),
    "SMTP_PORT": ("email", "smtp_port"),
    "SMTP_USER": ("email", "smtp_user"),
    "SMTP_PASSWORD": ("email", "smtp_password"),
    "EMAIL_TO": ("email", "email_to"),
    "ENABLE_EMAIL": ("email", "enable"),
    "FEISHU_APP_ID": ("feishu", "app_id"),
    "FEISHU_APP_SECRET": ("feishu", "app_secret"),
    "ENABLE_FEISHU": ("feishu", "enable"),
    "OUTPUT_DIR": ("script", "output_dir"),
    "LOG_DIR": ("script", "log_dir"),
    "ENABLE_ALERT": ("script", "enable_alert"),
    "DEGRADE_CONSECUTIVE_FAILURES": ("mode_switch", "consecutive_failures"),
    "DEGRADE_DAILY_FAILURE_RATE": ("mode_switch", "daily_failure_rate"),
    "DEGRADE_COOLDOWN_MINUTES": ("mode_switch", "cooldown_minutes"),
    "NEWS_COUNT": ("data_collection", "news_count"),
    "STOCK_RANKING_COUNT": ("data_collection", "stock_ranking_count"),
    "REQUEST_TIMEOUT": ("data_collection", "request_timeout"),
    "REQUEST_RETRIES": ("data_collection", "request_retries"),
}


# ============================================
# 工具函数
# ============================================
def deep_merge(base: Dict, override: Dict) -> Dict:
    """深度合并字典，override覆盖base"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_env_file(env_path: str) -> Dict[str, str]:
    """加载.env文件"""
    env_vars = {}
    if not os.path.exists(env_path):
        return env_vars

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue
                # 解析 KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env_vars[key] = value
                    # 同时设置到os.environ，方便其他模块读取
                    os.environ[key] = value
    except Exception as e:
        print(f"[WARN] 加载.env文件失败: {str(e)}", file=sys.stderr)

    return env_vars


def load_json_config(config_path: str) -> Dict:
    """加载config.json文件"""
    if not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # 移除注释字段（以//开头的键）
        config = {k: v for k, v in config.items() if not k.startswith('//')}
        return config
    except Exception as e:
        print(f"[WARN] 加载config.json失败: {str(e)}", file=sys.stderr)
        return {}


def convert_env_value(value: str, target_type: type):
    """转换环境变量值到目标类型"""
    if value is None:
        return None
    try:
        if target_type == bool:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif target_type == int:
            return int(value)
        elif target_type == float:
            return float(value)
        else:
            return value
    except (ValueError, TypeError):
        return None


def apply_env_vars(config: Dict) -> Dict:
    """应用环境变量到配置"""
    result = config.copy()
    for env_key, (section, config_key) in ENV_MAPPING.items():
        if env_key in os.environ:
            env_value = os.environ[env_key]
            # 获取默认值的类型
            default_value = DEFAULT_CONFIG.get(section, {}).get(config_key)
            target_type = type(default_value) if default_value is not None else str
            converted_value = convert_env_value(env_value, target_type)
            if converted_value is not None:
                if section not in result:
                    result[section] = {}
                result[section][config_key] = converted_value
    return result


# ============================================
# 主函数
# ============================================
def load_config(config_path: Optional[str] = None, env_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载配置（优先级：环境变量 > config.json > 默认值）

    Args:
        config_path: config.json路径，默认项目根目录/config.json
        env_path: .env路径，默认项目根目录/.env

    Returns:
        合并后的配置字典
    """
    # 确定文件路径
    if config_path is None:
        config_path = os.path.join(PROJECT_DIR, "config.json")
    if env_path is None:
        env_path = os.path.join(PROJECT_DIR, ".env")

    # 1. 加载.env文件（会设置到os.environ）
    load_env_file(env_path)

    # 2. 从默认配置开始
    config = DEFAULT_CONFIG.copy()

    # 3. 合并config.json
    json_config = load_json_config(config_path)
    if json_config:
        config = deep_merge(config, json_config)

    # 4. 应用环境变量（优先级最高）
    config = apply_env_vars(config)

    return config


def validate_config(config: Dict, check_email: bool = True, check_feishu: bool = True) -> List[str]:
    """
    校验配置，返回错误列表

    Args:
        config: 配置字典
        check_email: 是否校验邮箱配置
        check_feishu: 是否校验飞书配置

    Returns:
        错误信息列表，空列表表示校验通过
    """
    errors = []

    if check_email and config.get("email", {}).get("enable", True):
        email = config.get("email", {})
        if not email.get("smtp_user"):
            errors.append("邮箱配置错误：缺少 smtp_user（发件人邮箱）")
        if not email.get("smtp_password"):
            errors.append("邮箱配置错误：缺少 smtp_password（邮箱授权码）")
        if not email.get("email_to"):
            errors.append("邮箱配置错误：缺少 email_to（收件人邮箱）")

    if check_feishu and config.get("feishu", {}).get("enable", True):
        feishu = config.get("feishu", {})
        if not feishu.get("app_id"):
            errors.append("飞书配置错误：缺少 app_id（飞书应用ID）")
        if not feishu.get("app_secret"):
            errors.append("飞书配置错误：缺少 app_secret（飞书应用密钥）")

    return errors


def print_config_summary(config: Dict):
    """打印配置摘要（隐藏敏感信息）"""
    print("=" * 50)
    print("配置摘要")
    print("=" * 50)

    email = config.get("email", {})
    print(f"邮箱:")
    print(f"  启用: {'是' if email.get('enable') else '否'}")
    print(f"  发件人: {email.get('smtp_user', '未配置')}")
    print(f"  收件人: {email.get('email_to', '未配置')}")
    print(f"  授权码: {'已配置' if email.get('smtp_password') else '未配置'}")
    print(f"  SMTP服务器: {email.get('smtp_host')}:{email.get('smtp_port')}")

    feishu = config.get("feishu", {})
    print(f"飞书:")
    print(f"  启用: {'是' if feishu.get('enable') else '否'}")
    print(f"  App ID: {feishu.get('app_id', '未配置')}")
    print(f"  App Secret: {'已配置' if feishu.get('app_secret') else '未配置'}")

    script = config.get("script", {})
    print(f"脚本:")
    print(f"  输出目录: {script.get('output_dir')}")
    print(f"  日志目录: {script.get('log_dir')}")
    print(f"  失败告警: {'启用' if script.get('enable_alert') else '禁用'}")

    print("=" * 50)


def get_config_value(config: Dict, path: str, default: Any = None) -> Any:
    """
    通过点分路径获取配置值

    Args:
        config: 配置字典
        path: 点分路径，如 "email.smtp_host"
        default: 默认值

    Returns:
        配置值
    """
    keys = path.split('.')
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


# ============================================
# 命令行入口
# ============================================
def main():
    parser = argparse.ArgumentParser(description='配置加载器')
    parser.add_argument('--config', help='config.json路径')
    parser.add_argument('--env', help='.env路径')
    parser.add_argument('--validate', action='store_true', help='校验配置')
    parser.add_argument('--summary', action='store_true', help='打印配置摘要')
    args = parser.parse_args()

    config = load_config(args.config, args.env)

    if args.summary:
        print_config_summary(config)

    if args.validate:
        errors = validate_config(config)
        if errors:
            print("配置校验失败：")
            for error in errors:
                print(f"  ❌ {error}")
            sys.exit(1)
        else:
            print("✅ 配置校验通过")

    if not args.summary and not args.validate:
        # 默认打印摘要
        print_config_summary(config)


if __name__ == "__main__":
    import argparse
    main()
