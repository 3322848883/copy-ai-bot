# -*- coding: utf-8 -*-
"""Mailhog 验证码读取 helper：轮询 mailhog v1 API，解析 multipart/base64 邮件体中的 6 位验证码。"""
from __future__ import annotations

import base64
import email
import logging
import re
import time
from email import policy

import httpx

logger = logging.getLogger("e2e.mailhog")

MAILHOG_BASE = "http://localhost:8025/api/v1/messages"

_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
# ★ 验证码在 HTML 中位于独立 div（font-size:32px 样式块内）
_HTML_CODE_RE = re.compile(r">\s*(\d{6})\s*</div>")


def _extract_codes(raw_body: str) -> list[str]:
    """从邮件原始体（multipart MIME）递归提取验证码。

    ★ 必须只从解码后的 HTML part 提取，避免 base64 原始块中的数字（如颜色 #334155）误匹配。
    优先用「>NNNNNN</div>」上下文（验证码渲染块）；兜底再用解码后的 6 位数字。
    """
    codes: list[str] = []
    try:
        msg = email.message_from_string(raw_body, policy=policy.default)
    except Exception:  # noqa: BLE001
        # 非 MIME：不直接全文匹配（可能是 base64 原文），返回空
        return []
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/html", "text/plain"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        if ctype == "text/html":
            codes.extend(_HTML_CODE_RE.findall(text))
    return codes


def read_code(email_addr: str, timeout_s: int = 30) -> str:
    """轮询 mailhog 直到收到目标邮箱邮件，返回 6 位验证码。
    ★ mailhog v1 API 直接返回 JSON 数组（非 {items:[]}）。
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = httpx.get(MAILHOG_BASE, timeout=5)
            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", [])
        except Exception:  # noqa: BLE001
            logger.warning("mailhog poll error", exc_info=True)
            time.sleep(1)
            continue
        for item in items:
            headers = (item.get("Content") or {}).get("Headers", {})
            to = (headers.get("To") or [""])[0]
            if email_addr.lower() in to.lower():
                raw = item.get("Raw", {}).get("Data", "") or ""
                # 兜底：Body 字段或 Raw.Data
                body = item.get("Content", {}).get("Body", "") or ""
                all_codes = _extract_codes(raw) or _extract_codes(body)
                if all_codes:
                    return all_codes[0]
        time.sleep(1)
    raise TimeoutError(f"mailhog 30s 内未收到 {email_addr} 的验证码邮件")


def purge() -> None:
    """清空 mailhog（测试开始前调用，避免历史邮件干扰）。"""
    try:
        httpx.delete(MAILHOG_BASE, timeout=5)
    except Exception:  # noqa: BLE001
        logger.warning("mailhog purge failed", exc_info=True)
