# -*- coding: utf-8 -*-
"""stage 02 — 注册激活：3 用户 × 注册→读码→验证→登录→风险揭示。
限流纪律：/v1/auth/ 10 次/分/IP，用户间 sleep 65s 分窗。
"""
from __future__ import annotations

import time

import pytest

from conftest import AUTH_GROUP_SLEEP, load_state, save_state
from helpers import mailhog

PASSWORD = "Test1234!"


def _mk_email(prefix: str) -> str:
    return f"e2e_{prefix}_{int(time.time())}@t.com"


@pytest.fixture(scope="module")
def users():
    ts = int(time.time())
    return {
        "a": f"e2e_a_{ts}@t.com",
        "b": f"e2e_b_{ts}@t.com",
        "c": f"e2e_c_{ts}@t.com",
    }


def _register_and_verify(api, email: str) -> str:
    """注册→读码→验证→登录，返回 access_token。"""
    resp = api.request("POST", "/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 201, f"注册失败: {resp.status_code} {resp.text}"
    code = mailhog.read_code(email)
    assert len(code) == 6 and code.isdigit()
    resp = api.request("POST", "/v1/auth/verify-email", json={"email": email, "code": code})
    assert resp.status_code == 200, f"验证失败: {resp.status_code} {resp.text}"
    resp = api.request("POST", "/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, f"登录失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("access_token")
    assert data.get("refresh_token")
    assert data.get("risk_disclosure_accepted") is False
    return data["access_token"]


def test_register_duplicate_conflict(api, users):
    """重复注册 → 409。用独立邮箱，避免污染用户 A/B/C 的完整流程。"""
    dup = f"e2e_dup_{int(time.time())}@t.com"
    resp = api.request("POST", "/v1/auth/register", json={"email": dup, "password": PASSWORD})
    assert resp.status_code == 201
    resp = api.request("POST", "/v1/auth/register", json={"email": dup, "password": PASSWORD})
    assert resp.status_code == 409, f"期望 409 冲突, 实际 {resp.status_code}"


def test_verify_wrong_code(api, users):
    resp = api.request("POST", "/v1/auth/verify-email", json={"email": users["a"], "code": "000000"})
    assert resp.status_code in (400, 401, 422), f"错码应 4xx: {resp.status_code} {resp.text}"


def test_user_a_full_flow(api, users, save):
    token = _register_and_verify(api, users["a"])
    resp = api.request("POST", "/v1/auth/accept-risk-disclosure", token=token)
    assert resp.status_code == 200
    assert resp.json().get("risk_disclosure_accepted") is True
    state = load_state()
    state["userA_email"] = users["a"]
    state["userA_token"] = token
    save(state)
    time.sleep(AUTH_GROUP_SLEEP)


def test_user_b_full_flow(api, users, save):
    token = _register_and_verify(api, users["b"])
    state = load_state()
    state["userB_email"] = users["b"]
    state["userB_token"] = token
    save(state)
    time.sleep(AUTH_GROUP_SLEEP)


def test_user_c_full_flow(api, users, save):
    token = _register_and_verify(api, users["c"])
    state = load_state()
    state["userC_email"] = users["c"]
    state["userC_token"] = token
    save(state)
    time.sleep(AUTH_GROUP_SLEEP)


def test_login_wrong_password(api, users):
    resp = api.request("POST", "/v1/auth/login", json={"email": users["a"], "password": "WrongPass1!"})
    assert resp.status_code in (400, 401), f"错误密码应 4xx: {resp.status_code}"
