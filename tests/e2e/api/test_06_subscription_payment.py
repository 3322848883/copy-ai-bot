# -*- coding: utf-8 -*-
"""stage 06 — 订阅与支付：套餐 → 建单 → TxHash 负路径(failed) → DB 置 manual → admin 确认 → 订阅激活。"""
from __future__ import annotations

import time

import pytest

from conftest import load_state, save_state
from helpers import db as db_helpers


def test_plans_list(api):
    resp = api.request("GET", "/v1/subscriptions/plans")
    assert resp.status_code == 200
    plans = {p["plan_id"]: p for p in resp.json()["plans"]}
    assert plans["trial_5u"]["price_usdt"] == 5.0
    assert plans["monthly_19_9u"]["price_usdt"] == 19.9


def test_userA_create_order(api, save):
    state = load_state()
    resp = api.request(
        "POST", "/v1/payments",
        json={"plan_id": "monthly_19_9u", "network": "trc20"},
        token=state["userA_token"],
    )
    assert resp.status_code == 200, f"建单失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["status"] == "pending"
    assert data["amount_usdt"] == 19.9
    assert data["required_confirmations"] == 12
    state["orderA_id"] = data["order_id"]
    save(state)


def test_userB_create_trial_order(api, save):
    state = load_state()
    resp = api.request(
        "POST", "/v1/payments",
        json={"plan_id": "trial_5u", "network": "trc20"},
        token=state["userB_token"],
    )
    assert resp.status_code == 200, f"建单失败: {resp.status_code} {resp.text}"
    assert resp.json()["status"] == "pending"
    state["orderB_id"] = resp.json()["order_id"]
    save(state)


def test_submit_tx_failed_negative(api):
    """prod 链客户端未接真实 RPC → submit_tx 校验失败 → 订单落 failed（预期负路径）。"""
    state = load_state()
    resp = api.request(
        "POST", f"/v1/payments/{state['orderA_id']}/tx",
        json={"tx_hash": "0x" + "ab" * 32},
        token=state["userA_token"],
    )
    # prod 链 NotImplementedError → _verify_tx_status False → PaymentError 4xx(422)
    assert resp.status_code in (400, 422), f"prod 链负路径应 4xx: {resp.status_code} {resp.text}"
    assert "交易状态异常" in resp.text


def test_userB_submit_tx_negative(api):
    """userB 订单同样走 failed 负路径，以便后续置 manual。"""
    state = load_state()
    resp = api.request(
        "POST", f"/v1/payments/{state['orderB_id']}/tx",
        json={"tx_hash": "0x" + "cd" * 32},
        token=state["userB_token"],
    )
    assert resp.status_code in (400, 422), f"prod 链负路径应 4xx: {resp.status_code} {resp.text}"
    assert "交易状态异常" in resp.text


@pytest.mark.asyncio
async def test_db_set_order_manual(save):
    state = load_state()
    res = await db_helpers.set_order_manual(state["orderA_id"])
    assert "UPDATE 1" in res, f"置 manual 失败: {res}"
    res_b = await db_helpers.set_order_manual(state["orderB_id"])
    assert "UPDATE 1" in res_b


def test_admin_manual_confirm_orderA(api, admin_token, save):
    state = load_state()
    resp = api.request(
        "POST", f"/admin/v1/payments/{state['orderA_id']}/manual",
        json={"status": "confirmed"},
        token=admin_token,
    )
    assert resp.status_code == 200, f"manual 确认失败: {resp.status_code} {resp.text}"
    assert resp.json()["status"] == "confirmed"
    # 再确认 → 状态机拒绝（422）
    resp2 = api.request(
        "POST", f"/admin/v1/payments/{state['orderA_id']}/manual",
        json={"status": "confirmed"},
        token=admin_token,
    )
    assert resp2.status_code in (400, 409, 422), f"重复确认应拒绝: {resp2.status_code}"


def test_admin_manual_confirm_orderB(api, admin_token):
    state = load_state()
    resp = api.request(
        "POST", f"/admin/v1/payments/{state['orderB_id']}/manual",
        json={"status": "confirmed"},
        token=admin_token,
    )
    assert resp.status_code == 200 and resp.json()["status"] == "confirmed"


def test_subscription_active_after_payment(api):
    state = load_state()
    for email_key, expect_plan in (("userA_token", "monthly_19_9u"), ("userB_token", "trial_5u")):
        resp = api.request("GET", "/v1/subscriptions/me", token=state[email_key])
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active") is True, f"{email_key} 订阅未激活: {data}"
        assert data.get("plan_id") == expect_plan


def test_trial_limit_conflict(api):
    """trial_5u 限购 1 次：userB 再建 → 409。"""
    state = load_state()
    resp = api.request(
        "POST", "/v1/payments",
        json={"plan_id": "trial_5u", "network": "trc20"},
        token=state["userB_token"],
    )
    assert resp.status_code == 409, f"试用限购应 409: {resp.status_code} {resp.text}"


def test_invite_reward_triggered(api):
    """userA 邀请 userB → userB 支付后 userA 得 10% 奖励（verifying）。"""
    state = load_state()
    resp = api.request("GET", "/v1/rewards/ledger", token=state["userA_token"])
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    hit = [i for i in items if i.get("source_user_id") and i.get("amount_usdt") == 0.5]
    assert hit, f"应有 0.5U 邀请奖励: {items[:3]}"
