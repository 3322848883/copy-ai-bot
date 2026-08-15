# -*- coding: utf-8 -*-
"""stage 03 — 身份：选所 / 好友码 / G27 交易所邀请码。"""
from __future__ import annotations

from conftest import load_state, save_state


def test_choose_exchange(api, save):
    state = load_state()
    token = state["userA_token"]
    resp = api.request("POST", "/v1/identity/choose-exchange", json={"exchange": "gate"}, token=token)
    assert resp.status_code == 200
    assert resp.json().get("exchange") == "gate"
    state["userA_exchange"] = "gate"
    save(state)


def test_choose_exchange_duplicate_conflict(api):
    state = load_state()
    resp = api.request("POST", "/v1/identity/choose-exchange", json={"exchange": "gate"}, token=state["userA_token"])
    assert resp.status_code == 409, f"重复选所应 409: {resp.status_code} {resp.text}"


def test_get_invite_code(api, save):
    state = load_state()
    resp = api.request("GET", "/v1/referrals/code", token=state["userA_token"])
    assert resp.status_code == 200
    code = resp.json().get("code")
    assert code and len(code) >= 4
    state["userA_invite_code"] = code
    save(state)


def test_bind_invite_ok(api, save):
    state = load_state()
    resp = api.request("POST", "/v1/identity/bind-invite", json={"code": state["userA_invite_code"]}, token=state["userB_token"])
    assert resp.status_code == 200, f"绑定好友码失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("invite_code") == state["userA_invite_code"]


def test_bind_self_invite_conflict(api):
    state = load_state()
    resp = api.request("POST", "/v1/identity/bind-invite", json={"code": state["userA_invite_code"]}, token=state["userA_token"])
    assert resp.status_code == 409, f"自邀应 409: {resp.status_code} {resp.text}"


def test_bind_invalid_invite(api):
    state = load_state()
    resp = api.request("POST", "/v1/identity/bind-invite", json={"code": "NOPE9999"}, token=state["userC_token"])
    assert resp.status_code in (400, 404), f"无效码应 4xx: {resp.status_code} {resp.text}"


# ── ★ G27 交易所邀请码（admin 先建码 → userA 绑定）──
def test_g27_admin_create_code(api, admin_token, save):
    import time

    state = load_state()
    code = f"E2E{int(time.time()) % 100000:05d}"
    resp = api.request(
        "POST", "/admin/v1/exchange-invites",
        json={"exchange": "gate", "code": code, "max_binds": 5, "remark": "e2e"},
        token=admin_token,
    )
    assert resp.status_code == 200, f"建码失败: {resp.status_code} {resp.text}"
    state["g27_code"] = code
    save(state)


def test_g27_bind_ok(api, save):
    state = load_state()
    resp = api.request(
        "POST", "/v1/identity/bind-exchange-invite",
        json={"exchange": "gate", "code": state["g27_code"]},
        token=state["userA_token"],
    )
    assert resp.status_code == 200, f"G27 绑定失败: {resp.status_code} {resp.text}"
    assert resp.json().get("message") == "交易所邀请码绑定成功"


def test_g27_bind_wrong_exchange(api):
    state = load_state()
    resp = api.request(
        "POST", "/v1/identity/bind-exchange-invite",
        json={"exchange": "binance", "code": state["g27_code"]},
        token=state["userB_token"],
    )
    assert resp.status_code in (400, 422), f"错所码应 4xx: {resp.status_code} {resp.text}"
