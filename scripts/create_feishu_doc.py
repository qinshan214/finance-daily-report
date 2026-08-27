#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书文档生成脚本
通过飞书开放API将Markdown内容生成为飞书文档，不依赖AI。

使用方式：
    export FEISHU_APP_ID="cli_xxxxxxxx"
    export FEISHU_APP_SECRET="xxxxxxxx"
    python3 create_feishu_doc.py --title "财经日报-2026年08月28日" --content-file report.md
    或
    python3 create_feishu_doc.py --title "标题" --content "# 文档内容"

环境变量：
    FEISHU_APP_ID: 飞书应用 App ID
    FEISHU_APP_SECRET: 飞书应用 App Secret
"""

import requests
import json
import argparse
import os
import sys
import time
import re
from datetime import datetime


# ============================================
# 配置
# ============================================
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

# Token 缓存
_token_cache = {"token": None, "expire_time": 0}


def log(level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


# ============================================
# Token 管理
# ============================================
def get_tenant_access_token():
    """获取 tenant_access_token（带缓存）"""
    now = time.time()
    if _token_cache["token"] and _token_cache["expire_time"] > now + 60:
        return _token_cache["token"]

    if not APP_ID or not APP_SECRET:
        log("ERROR", "未设置 FEISHU_APP_ID 或 FEISHU_APP_SECRET 环境变量")
        return None

    url = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            token = data["tenant_access_token"]
            expire = data.get("expire", 7200)
            _token_cache["token"] = token
            _token_cache["expire_time"] = now + expire
            log("INFO", "获取 tenant_access_token 成功")
            return token
        else:
            log("ERROR", f"获取 token 失败: {data.get('msg', '未知错误')}")
            return None
    except Exception as e:
        log("ERROR", f"获取 token 异常: {str(e)}")
        return None


def get_headers(token):
    """获取请求头"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


# ============================================
# 文档创建
# ============================================
def create_document(token, title):
    """创建空白飞书文档（新版文档 docx）"""
    url = f"{FEISHU_BASE_URL}/docx/v1/documents"
    payload = {"title": title}

    try:
        resp = requests.post(url, headers=get_headers(token), json=payload, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            doc_id = data["data"]["document"]["document_id"]
            log("INFO", f"文档创建成功: {doc_id}")
            return doc_id
        else:
            log("ERROR", f"创建文档失败: {data.get('msg', '未知错误')}")
            return None
    except Exception as e:
        log("ERROR", f"创建文档异常: {str(e)}")
        return None


def set_document_permission(token, doc_id, link_share="tenant_readable"):
    """
    设置文档公共权限

    Args:
        token: tenant_access_token
        doc_id: 文档ID
        link_share: 链接分享权限
            - "tenant_readable": 组织内获得链接的人可阅读（默认）
            - "tenant_editable": 组织内获得链接的人可编辑
            - "anyone_readable": 互联网获得链接的人可阅读
            - "anyone_editable": 互联网获得链接的人可编辑
            - "closed": 关闭链接分享
    """
    # type 参数必须放在 URL 查询参数中
    url = f"{FEISHU_BASE_URL}/drive/v1/permissions/{doc_id}/public?type=docx"
    payload = {
        "external_access_entity": "open",  # 允许外部用户访问
        "link_share_entity": link_share,
        "comment_entity": "anyone_can_view",  # 任何人可查看评论
        "copy_entity": "anyone_can_view",     # 任何人可复制
        "share_entity": "anyone",              # 任何人可分享
        "manage_collaborator_entity": "collaborator_can_view",  # 协作者可查看协作者
    }

    try:
        resp = requests.patch(url, headers=get_headers(token), json=payload, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            log("INFO", f"文档权限设置成功: {link_share}")
            return True
        else:
            log("WARN", f"文档权限设置失败: {data.get('msg', '未知错误')} (code={data.get('code')})")
            return False
    except Exception as e:
        log("WARN", f"文档权限设置异常: {str(e)}")
        return False


def transfer_document_owner(token, doc_id, user_open_id):
    """
    转移文档所有者给指定用户

    Args:
        token: tenant_access_token
        doc_id: 文档ID
        user_open_id: 目标用户的 open_id
    """
    url = f"{FEISHU_BASE_URL}/drive/v1/files/{doc_id}/transfer_owner"
    payload = {
        "type": "docx",
        "owner_id": user_open_id,
        "owner_id_type": "open_id",
    }

    try:
        resp = requests.post(url, headers=get_headers(token), json=payload, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            log("INFO", f"文档所有者转移成功: {user_open_id}")
            return True
        else:
            log("WARN", f"文档所有者转移失败: {data.get('msg', '未知错误')} (code={data.get('code')})")
            return False
    except Exception as e:
        log("WARN", f"文档所有者转移异常: {str(e)}")
        return False


def get_document_url(doc_id):
    """获取文档访问链接"""
    return f"https://bytedance.larkoffice.com/docx/{doc_id}"


# ============================================
# 内容插入（Markdown 转飞书文档块）
# ============================================
def markdown_to_blocks(markdown_text):
    """
    将 Markdown 文本转换为飞书文档块结构
    支持：标题（# ## ###）、段落、列表（- 或 1.）、分割线（---）
    """
    blocks = []
    lines = markdown_text.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()

        # 空行跳过
        if not line.strip():
            i += 1
            continue

        # 分割线（转换为文本段落）
        if line.strip() in ['---', '***', '___']:
            blocks.append(create_text_block("—" * 30))
            i += 1
            continue

        # 标题
        if line.startswith('# '):
            blocks.append(create_heading_block(line[2:], 1))
            i += 1
            continue
        if line.startswith('## '):
            blocks.append(create_heading_block(line[3:], 2))
            i += 1
            continue
        if line.startswith('### '):
            blocks.append(create_heading_block(line[4:], 3))
            i += 1
            continue
        if line.startswith('#### '):
            blocks.append(create_heading_block(line[5:], 4))
            i += 1
            continue

        # 引用（转换为文本段落）
        if line.startswith('> '):
            quote_lines = [line[2:]]
            i += 1
            while i < len(lines) and lines[i].startswith('> '):
                quote_lines.append(lines[i][2:])
                i += 1
            blocks.append(create_text_block("> " + '\n> '.join(quote_lines)))
            continue

        # 无序列表（转换为文本段落，前缀加"- "）
        if line.strip().startswith('- ') or line.strip().startswith('* '):
            list_items = []
            while i < len(lines):
                curr = lines[i].strip()
                if curr.startswith('- ') or curr.startswith('* '):
                    list_items.append(curr[2:])
                    i += 1
                elif curr == '':
                    i += 1
                    break
                else:
                    break
            for item in list_items:
                blocks.append(create_text_block("• " + item))
            continue

        # 有序列表（转换为文本段落，前缀加数字）
        if len(line.strip()) > 2 and line.strip()[0].isdigit() and line.strip()[1] == '.':
            list_items = []
            while i < len(lines):
                curr = lines[i].strip()
                if len(curr) > 2 and curr[0].isdigit() and curr[1] == '.':
                    list_items.append(curr[2:].strip())
                    i += 1
                elif curr == '':
                    i += 1
                    break
                else:
                    break
            for idx, item in enumerate(list_items, 1):
                blocks.append(create_text_block(f"{idx}. " + item))
            continue

        # 代码块（转换为文本段落）
        if line.strip().startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结束的 ```
            blocks.append(create_text_block("代码:\n" + '\n'.join(code_lines)))
            continue

        # 表格（简单处理：连续的 | 行）
        if line.strip().startswith('|') and '|' in line[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            blocks.append(create_table_block(table_lines))
            continue

        # 普通段落（合并连续非空行）
        para_lines = [line]
        i += 1
        while i < len(lines):
            curr = lines[i].rstrip()
            if not curr.strip():
                i += 1
                break
            if curr.startswith(('#', '>', '- ', '* ', '---', '```')):
                break
            if len(curr) > 2 and curr[0].isdigit() and curr[1] == '.':
                break
            para_lines.append(curr)
            i += 1
        blocks.append(create_text_block(' '.join(para_lines)))

    return blocks


def get_full_style(bold=False):
    """获取完整的文本样式（飞书API要求所有字段）"""
    return {
        "bold": bold,
        "inline_code": False,
        "italic": False,
        "strikethrough": False,
        "underline": False,
    }


def parse_markdown_text(text):
    """解析Markdown文本，处理加粗等格式，返回飞书文本元素数组"""
    elements = []
    # 处理 **加粗** 标记
    parts = re.split(r'(\*\*[^*]+\*\*)', text)
    for part in parts:
        if not part:
            continue
        if part.startswith('**') and part.endswith('**'):
            # 加粗文本
            content = part[2:-2]
            elements.append({"text_run": {"content": content, "text_element_style": get_full_style(bold=True)}})
        else:
            elements.append({"text_run": {"content": part, "text_element_style": get_full_style()}})
    if not elements:
        elements.append({"text_run": {"content": text, "text_element_style": get_full_style()}})
    return elements


def create_text_element(text, bold=False):
    """创建文本元素（兼容旧接口）"""
    element = {"text_run": {"content": text, "text_element_style": {}}}
    if bold:
        element["text_run"]["text_element_style"]["bold"] = True
    return element


def create_heading_block(text, level):
    """创建标题块"""
    field_map = {1: "heading1", 2: "heading2", 3: "heading3", 4: "heading4"}
    type_map = {1: 3, 2: 4, 3: 5, 4: 6}
    field = field_map.get(level, "heading3")
    block_type = type_map.get(level, 5)
    return {
        "block_type": block_type,
        field: {"elements": parse_markdown_text(text), "style": {}},
    }


def create_text_block(text):
    """创建文本段落块"""
    return {
        "block_type": 2,
        "text": {"elements": parse_markdown_text(text), "style": {}},
    }


def create_quote_block(text):
    """创建引用块"""
    return {
        "block_type": 34,
        "quote_container": {"elements": parse_markdown_text(text)},
    }


def create_bullet_list_block(items):
    """创建无序列表块（每个item一个块）"""
    blocks = []
    for item in items:
        blocks.append({
            "block_type": 14,
            "bullet": {"elements": parse_markdown_text(item), "style": {}},
        })
    return blocks


def create_ordered_list_block(items):
    """创建有序列表块"""
    blocks = []
    for item in items:
        blocks.append({
            "block_type": 15,
            "ordered": {"elements": parse_markdown_text(item), "style": {}},
        })
    return blocks


def create_code_block(code):
    """创建代码块"""
    return {
        "block_type": 14,
        "code": {"elements": parse_markdown_text(code), "style": {}},
    }


def create_table_block(table_lines):
    """简单表格处理：转换为文本段落"""
    if len(table_lines) < 2:
        return create_text_block(table_lines[0] if table_lines else "")

    # 解析表头
    headers = [h.strip() for h in table_lines[0].strip('|').split('|')]
    # 跳过分隔行（第二行）
    data_rows = []
    for line in table_lines[2:]:
        cells = [c.strip() for c in line.strip('|').split('|')]
        data_rows.append(cells)

    # 构建表格文本
    table_text = " | ".join(headers) + "\n"
    for row in data_rows:
        table_text += " | ".join(row) + "\n"

    return create_text_block(table_text)


def insert_blocks(token, doc_id, blocks):
    """向文档插入块（分批插入，每批最多50个）"""
    if not blocks:
        return True

    url = f"{FEISHU_BASE_URL}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"

    batch_size = 50
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i + batch_size]
        payload = {"children": batch}

        try:
            resp = requests.post(url, headers=get_headers(token), json=payload, timeout=15)
            data = resp.json()
            if data.get("code") == 0:
                log("INFO", f"插入块成功: {i+1}-{i+len(batch)}/{len(blocks)}")
            else:
                log("ERROR", f"插入块失败: {data.get('msg', '未知错误')}")
                log("ERROR", f"响应: {json.dumps(data, ensure_ascii=False)[:500]}")
                return False
        except Exception as e:
            log("ERROR", f"插入块异常: {str(e)}")
            return False

        time.sleep(0.3)  # 避免频率限制

    return True


# ============================================
# 文档权限设置
# ============================================
def set_doc_permission(token, doc_id):
    """设置文档权限为组织内可查看"""
    # 飞书文档权限设置 API
    url = f"{FEISHU_BASE_URL}/drive/v1/permissions/{doc_id}/public"
    payload = {
        "external_access_entity": "open",
        "security_entity": "anyone_can_view",
        "comment_entity": "anyone_can_view",
        "share_entity": "anyone",
        "link_share_entity": "tenant_readable",
    }

    try:
        resp = requests.patch(url, headers=get_headers(token), json=payload, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            log("INFO", "文档权限设置成功（组织内可查看）")
            return True
        else:
            log("WARN", f"文档权限设置失败（不影响文档创建）: {data.get('msg', '')}")
            return False
    except Exception as e:
        log("WARN", f"文档权限设置异常: {str(e)}")
        return False


# ============================================
# 主函数
# ============================================
def main():
    parser = argparse.ArgumentParser(description='飞书文档生成脚本')
    parser.add_argument('--title', '-t', required=True, help='文档标题')
    parser.add_argument('--content', '-c', help='文档内容（Markdown格式）')
    parser.add_argument('--content-file', '-f', help='文档内容文件路径（Markdown格式）')
    parser.add_argument('--permission', '-p', default='tenant_readable',
                        choices=['tenant_readable', 'tenant_editable', 'anyone_readable', 'anyone_editable', 'closed'],
                        help='文档权限（默认：组织内获得链接的人可阅读）')
    parser.add_argument('--no-permission', action='store_true', help='不设置文档权限')
    parser.add_argument('--transfer-owner', help='将文档所有者转移给指定用户的open_id')
    args = parser.parse_args()

    # 获取内容
    if args.content_file:
        if not os.path.exists(args.content_file):
            log("ERROR", f"内容文件不存在: {args.content_file}")
            sys.exit(1)
        with open(args.content_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
    elif args.content:
        markdown_content = args.content
    else:
        log("ERROR", "必须指定 --content 或 --content-file")
        sys.exit(1)

    log("INFO", "=" * 50)
    log("INFO", f"开始生成飞书文档: {args.title}")
    log("INFO", f"内容长度: {len(markdown_content)} 字符")

    # 1. 获取 token
    token = get_tenant_access_token()
    if not token:
        log("ERROR", "无法获取 token，终止")
        sys.exit(1)

    # 2. 创建文档
    doc_id = create_document(token, args.title)
    if not doc_id:
        log("ERROR", "文档创建失败，终止")
        sys.exit(1)

    # 3. 转换 Markdown 为块
    log("INFO", "转换 Markdown 为文档块...")
    blocks = markdown_to_blocks(markdown_content)
    log("INFO", f"生成 {len(blocks)} 个块")

    # 4. 插入块
    if blocks:
        success = insert_blocks(token, doc_id, blocks)
        if not success:
            log("WARN", "部分块插入失败，但文档已创建")

    # 5. 设置权限（默认设置，除非指定 --no-permission）
    if not args.no_permission:
        set_document_permission(token, doc_id, args.permission)

    # 6. 转移文档所有者（如果指定）
    if args.transfer_owner:
        transfer_document_owner(token, doc_id, args.transfer_owner)

    # 7. 输出结果
    doc_url = get_document_url(doc_id)
    log("INFO", "=" * 50)
    log("INFO", "文档生成完成！")
    log("INFO", f"文档 ID: {doc_id}")
    log("INFO", f"文档链接: {doc_url}")
    log("INFO", "=" * 50)

    # 输出 JSON 格式结果，便于其他脚本调用
    result = {
        "success": True,
        "doc_id": doc_id,
        "url": doc_url,
        "title": args.title,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
