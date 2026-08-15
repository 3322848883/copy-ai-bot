# -*- coding: utf-8 -*-
"""stage 08 — 提现：预插 available 余额 → 门槛/地址/超额负路径 → 正路径 → admin 审核链。"""
from __future__ import annotations

import pytest

from conftest import load_state, save_state
from helpers import db as db_helpers

# TRC20 地址：T + 33 位 [1-9A-HJ-NP-Za-km-z]（无 0/O/I/l）——程序化生成，保证长度
import re as _re

_TRC20_CHARSET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
VALID_TRC20 = "T" + ("A1b2C3d4E5f6G7h8J9KmNpQrStUvWxYz" * 3)[:33]
assert len(VALID_TRC20) == 34 and VALID_TRC20.startswith("T") and _re.fullmatch(r"^T[1-9A-HJ-NP-Za-km-z]{33}$", VALID_TRC20), VALID_TRC20


@pytest.mark.asyncio
async def test_prep_available_balance(save):
    """userA 预插 50U available 奖励（模拟成熟邀请奖励）。"""
    state = load_state()
    ua = await db_helpers.get_user_id_by_email(state["userA_email"])
    ub = await db_helpers.get_user_id_by_email(state["userB_email"])
    assert ua and ub
    rid = await db_helpers.insert_available_reward(ua, ub, 50.0, state["orderB_id"])
    assert rid > 0
    state["userA_id"] = ua
    state["userB_id"] = ub
    save(state)


def test_balance_50(api):
    state = load_state()
    resp = api.request("GET", "/v1/rewards/balance", token=state["userA_token"])
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("available_usdt") == 50.0, f"可用余额应为 50: {data}"


def test_withdraw_below_min(api):
    state = load_state()
    resp = api.request(
        "POST", "/v1/withdrawals",
        json={"network": "trc20", "address": VALID_TRC20, "amount_usdt": 5.0},
        token=state["userA_token"],
    )
    assert resp.status_code in (400, 422), f"低于 10U 应拒绝: {resp.status_code} {resp.text}"
    assert "10" in resp.text


def test_withdraw_invalid_address(api):
    state = load_state()
    resp = api.request(
        "POST", "/v1/withdrawals",
        json={"network": "trc20", "address": "0x0000000000000000000000000000000000000000", "amount_usdt": 10.0},
        token=state["userA_token"],
    )
    assert resp.status_code in (400, 422), f"非法地址应拒绝: {resp.status_code} {resp.text}"
    assert "地址" in resp.text


def test_withdraw_over_balance(api):
    state = load_state()
    resp = api.request(
        "POST", "/v1/withdrawals",
        json={"network": "trc20", "address": VALID_TRC20, "amount_usdt": 60.0},
        token=state["userA_token"],
    )
    assert resp.status_code in (400, 422), f"超额应拒绝: {resp.status_code} {resp.text}"
    assert "余额不足" in resp.text


def test_withdraw_ok(api, save):
    state = load_state()
    resp = api.request(
        "POST", "/v1/withdrawals",
        json={"network": "trc20", "address": VALID_TRC20, "amount_usdt": 10.0},
        token=state["userA_token"],
    )
    assert resp.status_code == 200, f"提现申请失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["status"] == "pending_review"
    assert data["fee_usdt"] == 1.0
    state["withdrawal_id"] = data["id"]
    save(state)
    # 提现后：available 减少、withdrawing 覆盖 ≥10（系统按整张 Reward 锁定，50U 整张转 withdrawing）
    resp2 = api.request("GET", "/v1/rewards/balance", token=state["userA_token"])
    d2 = resp2.json()
    assert d2.get("withdrawing_usdt") >= 10.0, f"withdrawing 应 ≥10: {d2}"
    assert d2.get("available_usdt") < 50.0, f"available 应减少: {d2}"


def test_admin_approve_withdrawal(api, admin_token):
    state = load_state()
    resp = api.request(
        "POST", f"/admin/v1/withdrawals/{state['withdrawal_id']}/approve", json={}, token=admin_token
    )
    assert resp.status_code == 200, f"approve 失败: {resp.status_code} {resp.text}"
    assert resp.json()["status"] == "approved"


def test_admin_fill_tx(api, admin_token):
    state = load_state()
    tx = "0x" + "cd" * 32
    resp = api.request(
        "POST", f"/admin/v1/withdrawals/{state['withdrawal_id']}/fill-tx",
        json={"tx_hash": tx}, token=admin_token,
    )
    assert resp.status_code == 200, f"fill-tx 失败: {resp.status_code} {resp.text}"
    assert resp.json()["status"] == "paid"
    # 用户侧可见 tx_hash
    resp2 = api.request("GET", f"/v1/withdrawals/{state['withdrawal_id']}", token=state["userA_token"])
    assert resp2.status_code == 200
    assert resp2.json().get("tx_hash") == tx


def test_withdrawal_list(api):
    state = load_state()
    resp = api.request("GET", "/v1/withdrawals", token=state["userA_token"])
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    hit = [w for w in items if w["id"] == state["withdrawal_id"]]
    assert hit and hit[0]["status"] == "paid"
