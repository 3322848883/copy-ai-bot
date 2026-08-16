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


# ── 防循环：互邀 2 元环 A↔B（A 绑 B 的码，B 已绑 A 的码）──
def test_get_userb_invite_code(api, save):
    state = load_state()
    resp = api.request("GET", "/v1/referrals/code", token=state["userB_token"])
    assert resp.status_code == 200
    state["userB_invite_code"] = resp.json().get("code")
    save(state)


def test_mutual_invite_cycle_rejected(api):
    """★ 验收门：A→B→A 互邀应被循环校验拒绝。"""
    state = load_state()
    resp = api.request(
        "POST", "/v1/identity/bind-invite",
        json={"code": state["userB_invite_code"]},
        token=state["userA_token"],
    )
    assert resp.status_code == 409, f"互邀环应 409: {resp.status_code} {resp.text}"


def test_one_time_bind_rejected(api):
    """★ T1.4 一次性绑定：userB 已绑 userA 码，再绑 userC 码应 409。"""
    state = load_state()
    resp = api.request("GET", "/v1/referrals/code", token=state["userC_token"])
    assert resp.status_code == 200
    userC_code = resp.json().get("code")
    resp = api.request(
        "POST", "/v1/identity/bind-invite",
        json={"code": userC_code},
        token=state["userB_token"],
    )
    assert resp.status_code == 409, f"重复绑定应 409: {resp.status_code} {resp.text}"


# ── ★ G06 平台池自动识别 ──
@pytest.mark.asyncio
async def test_g06_pool_auto_mark_sub_account(api, save):
    """★ 验收门：填入 PlatformPool 码 + 匹配交易所 → 自动标记 sub_account。"""
    import time
    from helpers import db as db_helpers

    state = load_state()
    pool_code = f"POOL{int(time.time()) % 100000:05d}"
    await db_helpers.prep_platform_pool(pool_code, exchange="gate")
    # userC 先选所 gate，再绑平台池码
    resp = api.request(
        "POST", "/v1/identity/choose-exchange", json={"exchange": "gate"}, token=state["userC_token"]
    )
    assert resp.status_code == 200, f"userC 选所失败: {resp.status_code} {resp.text}"
    resp = api.request(
        "POST", "/v1/identity/bind-invite", json={"code": pool_code}, token=state["userC_token"]
    )
    assert resp.status_code == 200, f"平台池码绑定失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("sub_account") is True, f"应标记 sub_account: {data}"
    uc = await db_helpers.get_user_id_by_email(state["userC_email"])
    assert await db_helpers.get_identity_type(uc) == "sub_account"


@pytest.mark.asyncio
async def test_g06_normal_code_keeps_normal(api):
    """★ 验收门：普通好友码不触发自动标记，保持 normal。"""
    from helpers import db as db_helpers

    state = load_state()
    ub = await db_helpers.get_user_id_by_email(state["userB_email"])
    assert await db_helpers.get_identity_type(ub) == "normal", "普通好友码应保持 normal 身份"


@pytest.mark.asyncio
async def test_friend_bind_audit_logged(api):
    """★ 验收门：好友码绑定写 audit-log（T1.4 audit-log 写入）。"""
    from helpers import db as db_helpers

    state = load_state()
    ub = await db_helpers.get_user_id_by_email(state["userB_email"])
    n = await db_helpers.count_audit_events(ub, "identity.bind_invite")
    assert n >= 1, f"好友码绑定应产生 audit-log: {n}"
