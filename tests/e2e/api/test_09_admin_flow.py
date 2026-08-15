# -*- coding: utf-8 -*-
"""stage 09 — 后台管理：admin 登录/RBAC/用户冻结/支付单/审计留痕。"""
from __future__ import annotations

from conftest import load_state, save_state


def test_admin_login_role(api, admin_token):
    """验证 admin token 的 JWT 载荷含 role=admin（避免重复登录触发限流 429）。"""
    import base64
    import json

    assert admin_token
    payload_b64 = admin_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    assert payload.get("role") == "admin"
    assert payload.get("aud") == "admin"


def test_regular_user_forbidden_admin(api):
    """普通用户 token 打 admin 接口 → 403。"""
    state = load_state()
    resp = api.request("GET", "/admin/v1/users", token=state["userA_token"])
    assert resp.status_code in (401, 403), f"普通用户应被拒: {resp.status_code} {resp.text}"


def test_admin_users_list(api, admin_token):
    state = load_state()
    resp = api.request("GET", "/admin/v1/users", params={"q": "e2e_a_"}, token=admin_token)
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    hit = [u for u in items if u["email"] == state["userA_email"]]
    assert hit, "后台用户列表应含 userA"


def test_admin_freeze_unfreeze(api, admin_token):
    """冻结 userC → 其登录被拒 → 解冻恢复。"""
    state = load_state()
    resp = api.request("GET", "/admin/v1/users", params={"q": "e2e_c_"}, token=admin_token)
    uid = [u for u in resp.json().get("items", []) if u["email"] == state["userC_email"]][0]["id"]

    resp = api.request("PATCH", f"/admin/v1/users/{uid}/freeze", json={"frozen": True}, token=admin_token)
    assert resp.status_code == 200
    resp = api.request("POST", "/v1/auth/login", json={"email": state["userC_email"], "password": "Test1234!"})
    assert resp.status_code in (400, 401, 403), f"冻结后登录应被拒: {resp.status_code} {resp.text}"
    resp = api.request("PATCH", f"/admin/v1/users/{uid}/freeze", json={"frozen": False}, token=admin_token)
    assert resp.status_code == 200


def test_admin_payments_list(api, admin_token):
    state = load_state()
    resp = api.request("GET", "/admin/v1/payments", params={"status": "confirmed"}, token=admin_token)
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    ids = {i["id"] for i in items}
    assert state["orderA_id"] in ids and state["orderB_id"] in ids, "confirmed 支付单应含 A/B 订单"


def test_admin_exchange_invites_list(api, admin_token):
    state = load_state()
    resp = api.request("GET", "/admin/v1/exchange-invites", params={"exchange": "gate"}, token=admin_token)
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    hit = [c for c in items if c["code"] == state["g27_code"]]
    assert hit and hit[0]["bind_count"] >= 1, "G27 码应存在且已绑定 ≥1"


def test_admin_audit_has_key_actions(api, admin_token):
    resp = api.request("GET", "/admin/v1/audit", token=admin_token)
    assert resp.status_code == 200
    actions = [a.get("action") for a in resp.json().get("items", [])]
    assert "payment.manual_confirmed" in actions or "payment.manual_confirm" in actions, \
        f"审计应含支付人工确认: {actions[:10]}"
    assert "strategy.force_list" in actions, f"审计应含策略强上架: {actions[:10]}"
    assert "identity.bind_exchange_invite" in actions
    assert any("withdrawal" in a for a in actions), "审计应含提现动作"


def test_admin_signal_session_status(api, admin_token):
    resp = api.request("GET", "/admin/v1/signal-session/status", token=admin_token)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("enabled") is True, f"signal_session 应启用: {data}"
