#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用工具模块：重试机制、日志、配置等
"""

import time
import functools
import logging
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def retry(max_attempts=3, delay=2, backoff=2, exceptions=(Exception,)):
    """
    重试装饰器
    
    Args:
        max_attempts: 最大重试次数（默认3次）
        delay: 初始延迟时间（秒，默认2秒）
        backoff: 延迟倍增系数（默认2，即每次重试延迟翻倍）
        exceptions: 需要重试的异常类型（默认所有异常）
    
    用法:
        @retry(max_attempts=3, delay=2)
        def fetch_data():
            # 可能失败的操作
            pass
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            
            while attempt < max_attempts:
                try:
                    attempt += 1
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(f"{func.__name__} 第{attempt}次尝试成功")
                    return result
                except exceptions as e:
                    if attempt >= max_attempts:
                        logger.error(f"{func.__name__} 重试{max_attempts}次后仍然失败: {e}")
                        raise
                    
                    logger.warning(f"{func.__name__} 第{attempt}次尝试失败: {e}，{current_delay}秒后重试...")
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            return None
        return wrapper
    return decorator


def retry_request(session, url, method='GET', max_attempts=3, delay=2, backoff=2, **kwargs):
    """
    带重试的HTTP请求
    
    Args:
        session: requests.Session 对象
        url: 请求URL
        method: 请求方法（GET/POST）
        max_attempts: 最大重试次数
        delay: 初始延迟时间
        backoff: 延迟倍增系数
        **kwargs: 传递给 requests 的其他参数
    
    Returns:
        requests.Response 对象
    
    Raises:
        最后一次重试仍然失败时抛出异常
    """
    import requests
    
    attempt = 0
    current_delay = delay
    
    while attempt < max_attempts:
        try:
            attempt += 1
            if method.upper() == 'GET':
                resp = session.get(url, timeout=kwargs.pop('timeout', 15), **kwargs)
            else:
                resp = session.post(url, timeout=kwargs.pop('timeout', 15), **kwargs)
            
            # 如果状态码是5xx或429，重试
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt >= max_attempts:
                    logger.error(f"请求 {url} 状态码 {resp.status_code}，重试{max_attempts}次后仍然失败")
                    resp.raise_for_status()
                
                logger.warning(f"请求 {url} 状态码 {resp.status_code}，{current_delay}秒后重试...")
                time.sleep(current_delay)
                current_delay *= backoff
                continue
            
            if attempt > 1:
                logger.info(f"请求 {url} 第{attempt}次尝试成功")
            
            return resp
            
        except (requests.exceptions.Timeout, 
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError) as e:
            if attempt >= max_attempts:
                logger.error(f"请求 {url} 网络错误，重试{max_attempts}次后仍然失败: {e}")
                raise
            
            logger.warning(f"请求 {url} 网络错误: {e}，{current_delay}秒后重试...")
            time.sleep(current_delay)
            current_delay *= backoff
    
    return None


def ensure_dir(dir_path):
    """确保目录存在"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    return dir_path


def load_env_file(env_path='.env'):
    """加载 .env 文件到环境变量"""
    if not os.path.exists(env_path):
        logger.warning(f"环境变量文件不存在: {env_path}")
        return
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            
            if key and key not in os.environ:
                os.environ[key] = value


if __name__ == '__main__':
    # 测试重试装饰器
    @retry(max_attempts=3, delay=1)
    def test_func():
        import random
        if random.random() < 0.5:
            raise Exception("随机失败")
        return "成功"
    
    try:
        result = test_func()
        print(f"结果: {result}")
    except Exception as e:
        print(f"最终失败: {e}")
