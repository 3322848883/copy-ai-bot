# -*- coding: utf-8 -*-
"""stage 01 — 数据准备：清限流、预插 Trader+画像、清 mailhog、写 state。"""
from __future__ import annotations

import time

import pytest

from helpers import db as db_helpers
from helpers import mailhog
from helpers import redis_tool
from conftest import load_state, save_state


def test_clear_rate_limits():
    n = redis_tool.clear_rate_limits()
    assert n >= 0


def test_purge_mailhog():
    mailhog.purge()
    # 清空后应无残留（mailhog v1 API 返回 JSON 数组）
    import httpx
    resp = httpx.get("http://localhost:8025/api/v1/messages", timeout=10)
    data = resp.json()
    items = data if isinstance(data, list) else data.get("items", [])
    assert items == []


@pytest.mark.asyncio
async def test_prep_trader_and_state(save):
    ts = int(time.time())
    trader_id_db = await db_helpers.prep_trader(trader_id=f"e2e_trader_{ts}", name="E2E测试带单员")
    assert trader_id_db > 0
    state = load_state()
    state["trader_id"] = trader_id_db
    state["trader_external_id"] = f"e2e_trader_{ts}"
    save(state)
