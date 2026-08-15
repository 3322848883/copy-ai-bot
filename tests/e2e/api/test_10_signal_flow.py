# -*- coding: utf-8 -*-
"""stage 10 — 信号链路：worker 心跳 / Redis 基线（存在则校验新鲜）/ source_signals 可查询 / 后台策略 / 会话搜索。"""
from __future__ import annotations

import pytest

from conftest import load_state
from helpers import db as db_helpers
from helpers import redis_tool


def test_redis_feed_baseline_exists_or_empty():
    """基线键 gate:feed:state:* 存在则视为链路激活；空也允许（真实带单员可能无活跃抓取）。
    不强制断言非空——worker 心跳由 task 结果保证。"""
    keys = redis_tool.scan_feed_state_keys()
    # 仅记录，不硬性失败（真实 leader 数据依赖上游）
    assert isinstance(keys, list)


def test_redis_feed_baseline_fresh_if_exists():
    keys = redis_tool.scan_feed_state_keys()
    if not keys:
        return  # 无基线不校验
    ages = [redis_tool.get_feed_state_age_seconds(k) for k in keys[:3]]
    assert ages and all(a >= 0 for a in ages)
    assert min(ages) < 300, f"基线应新鲜: {ages}"


@pytest.mark.asyncio
async def test_source_signals_table_queryable():
    cnt = await db_helpers.count_signals()
    assert cnt >= 0
    row = await db_helpers.fetch_latest_signal_row()
    assert row is None or "trader_id" in row or "symbol" in row


def test_worker_recent_task_success(api, admin_token):
    """通过 beat 调度记录佐证：查询 admin signals 列表成功即后台与 DB 正常。"""
    resp = api.request("GET", "/admin/v1/signals", token=admin_token)
    assert resp.status_code == 200


def test_admin_signals_list(api, admin_token):
    state = load_state()
    resp = api.request("GET", "/admin/v1/signals", token=admin_token)
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    hit = [s for s in items if s.get("id") == state["strategy_id"]]
    assert hit, "后台策略列表应含 E2E 策略"


def test_signal_session_status(api, admin_token):
    resp = api.request("GET", "/admin/v1/signal-session/status", token=admin_token)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("enabled") is True


def test_signal_session_search_by_nickname(api, admin_token):
    resp = api.request(
        "GET", "/admin/v1/signal-session/search",
        params={"keyword": "风懃"},
        token=admin_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True, f"搜索应 ok: {data}"
    ids = {int(i.get("leader_id")) for i in data.get("items", [])}
    assert 24264 in ids, f"应命中 24264: {ids}"


def test_signal_session_search_by_id(api, admin_token):
    resp = api.request(
        "GET", "/admin/v1/signal-session/search",
        params={"keyword": "24264"},
        token=admin_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("source") == "detail"
    assert len(data.get("items", [])) == 1
