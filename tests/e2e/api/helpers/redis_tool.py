# -*- coding: utf-8 -*-
"""Redis 工具 helper：清理限流键（不 FLUSHDB，保留 celery broker 与信号基线）。"""
from __future__ import annotations

import os

import redis

REDIS_URL = os.environ.get("E2E_REDIS_URL", "redis://localhost:6381/0")


def clear_rate_limits() -> int:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    keys = [k for k in r.scan_iter("ratelimit:*")]
    if keys:
        r.delete(*keys)
    return len(keys)


def scan_feed_state_keys() -> list[str]:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    return [k for k in r.scan_iter("gate:feed:state:*")]


def get_feed_state_age_seconds(key: str) -> int:
    """读基线 JSON 的 updated_at，返回距今秒数。"""
    import json
    import time
    from datetime import datetime, timezone

    r = redis.from_url(REDIS_URL, decode_responses=True)
    raw = r.get(key)
    if not raw:
        return -1
    try:
        data = json.loads(raw)
        ts = data.get("updated_at") or data.get("ts")
        if isinstance(ts, (int, float)):
            return int(time.time() - ts)
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:  # noqa: BLE001
        return -1
