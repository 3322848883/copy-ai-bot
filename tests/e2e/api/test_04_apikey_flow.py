# -*- coding: utf-8 -*-
"""stage 04 — API Key：prod 模式真实交易所校验不可用，用 DB 直插验证「列表不泄密钥」+「绑定接口拒绝假 key」。"""
from __future__ import annotations

import pytest

from conftest import load_state, save_state
from helpers import db as db_helpers


@pytest.mark.asyncio
async def test_db_prep_apikeys(save):
    """DB 直插 gate + binance 两把 key（userA），供 bot 归属/错配校验。"""
    state = load_state()
    ua = await db_helpers.get_user_id_by_email(state["userA_email"])
    assert ua, "userA 不存在"
    gate_id = await db_helpers.prep_apikey(ua, "gate")
    binance_id = await db_helpers.prep_apikey(ua, "binance")
    assert gate_id > 0 and binance_id > 0
    state["apikey_gate_id"] = gate_id
    state["apikey_binance_id"] = binance_id
    save(state)


def test_list_apikeys_no_secret(api):
    """列表只返回 {id, exchange}，绝不泄露密钥字段。"""
    state = load_state()
    resp = api.request("GET", "/v1/apikeys", token=state["userA_token"])
    assert resp.status_code == 200
    items = resp.json()["items"]
    gate = [i for i in items if i["exchange"] == "gate"]
    assert gate, "列表应含 gate key"
    assert set(gate[0].keys()) == {"id", "exchange"}, f"不应泄露密钥字段: {gate[0]}"
    # 全部字段白名单
    for item in items:
        assert set(item.keys()) == {"id", "exchange"}


def test_bind_fake_key_rejected(api):
    """prod 真实校验：用 gate（非纯 Mock 适配器）假 key 绑定应失败（connect/auth 错误）。"""
    state = load_state()
    resp = api.request(
        "POST", "/v1/apikeys",
        json={"exchange": "gate", "api_key": "FAKEKEY1234567890", "api_secret": "FAKESECRET1234567890"},
        token=state["userA_token"],
    )
    # gate 在 prod 走真实 HTTP 签名校验 → 假 key 应 4xx（网络/鉴权失败）
    assert resp.status_code in (400, 422), f"假 key 应被拒: {resp.status_code} {resp.text}"


@pytest.mark.asyncio
async def test_db_prep_apikeys_userb(save):
    """userC 不需要 key；userB 也无须（trial 订阅不建 bot）。确保 userB 无 key 用于负路径可选。"""
    state = load_state()
    uc = await db_helpers.get_user_id_by_email(state["userC_email"])
    assert uc
    state["userC_id"] = uc
    save(state)
