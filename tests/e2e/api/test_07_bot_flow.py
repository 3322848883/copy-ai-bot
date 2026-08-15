# -*- coding: utf-8 -*-
"""stage 07 — 跟单机器人：无订阅拦截 / 跨所错配 / API Key 错配 / 正路径(paper) / 同策略 409 / 状态切换。"""
from __future__ import annotations

from conftest import load_state, save_state


def _bot_payload(strategy_id: int, exchange: str, api_key_id: int, **kw):
    return {
        "strategy_id": strategy_id,
        "exchange": exchange,
        "api_key_id": api_key_id,
        "amount_mode": "percent",
        "percent": 20.0,
        "leverage": 10,
        "margin_mode": "isolated",
        "max_total_position_usdt": 10_000.0,
        "paper": True,
        **kw,
    }


def test_create_bot_without_subscription(api):
    """userC 无订阅 → 建 bot 拦截。"""
    state = load_state()
    resp = api.request(
        "POST", "/v1/bots",
        json=_bot_payload(state["strategy_id"], "gate", state["apikey_gate_id"]),
        token=state["userC_token"],
    )
    assert resp.status_code in (400, 422), f"无订阅应拦截: {resp.status_code} {resp.text}"
    assert "订阅" in resp.text


def test_create_bot_cross_exchange_mismatch(api):
    """策略源 gate + bot 交易所 binance → 跨所错配拦截。"""
    state = load_state()
    resp = api.request(
        "POST", "/v1/bots",
        json=_bot_payload(state["strategy_id"], "binance", state["apikey_binance_id"]),
        token=state["userA_token"],
    )
    assert resp.status_code in (400, 422), f"跨所错配应拦截: {resp.status_code} {resp.text}"
    assert "跨所错配" in resp.text


def test_create_bot_apikey_exchange_mismatch(api):
    """策略 gate + bot gate 但用 binance key → API Key 错配拦截。"""
    state = load_state()
    resp = api.request(
        "POST", "/v1/bots",
        json=_bot_payload(state["strategy_id"], "gate", state["apikey_binance_id"]),
        token=state["userA_token"],
    )
    assert resp.status_code in (400, 422), f"API Key 错配应拦截: {resp.status_code} {resp.text}"
    assert "API Key" in resp.text


def test_create_bot_ok(api, save):
    """正路径：gate + gate key + paper 沙箱 → active。"""
    state = load_state()
    resp = api.request(
        "POST", "/v1/bots",
        json=_bot_payload(state["strategy_id"], "gate", state["apikey_gate_id"]),
        token=state["userA_token"],
    )
    assert resp.status_code == 200, f"建 bot 失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["status"] == "active"
    assert data["paper"] is True
    state["bot_id"] = data["id"]
    save(state)


def test_create_bot_duplicate_strategy(api):
    """同策略已建 bot → 409。"""
    state = load_state()
    resp = api.request(
        "POST", "/v1/bots",
        json=_bot_payload(state["strategy_id"], "gate", state["apikey_gate_id"]),
        token=state["userA_token"],
    )
    assert resp.status_code == 409, f"重复策略应 409: {resp.status_code} {resp.text}"


def test_bot_status_pause_resume(api):
    state = load_state()
    bot_id = state["bot_id"]
    resp = api.request("PATCH", f"/v1/bots/{bot_id}/status", json={"status": "paused"}, token=state["userA_token"])
    assert resp.status_code == 200 and resp.json()["status"] == "paused"
    resp = api.request("PATCH", f"/v1/bots/{bot_id}/status", json={"status": "active"}, token=state["userA_token"])
    assert resp.status_code == 200 and resp.json()["status"] == "active"
    resp = api.request("PATCH", f"/v1/bots/{bot_id}/status", json={"status": "invalid"}, token=state["userA_token"])
    assert resp.status_code in (400, 422), f"非法 status 应 4xx: {resp.status_code}"


def test_bot_orders_positions_empty(api):
    state = load_state()
    bot_id = state["bot_id"]
    resp = api.request("GET", f"/v1/bots/{bot_id}/orders", token=state["userA_token"])
    assert resp.status_code == 200
    assert resp.json().get("items", []) == []
    resp = api.request("GET", f"/v1/bots/{bot_id}/positions", token=state["userA_token"])
    assert resp.status_code == 200
    assert resp.json().get("items", []) == []


def test_bot_list(api):
    state = load_state()
    resp = api.request("GET", "/v1/bots", token=state["userA_token"])
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    hit = [b for b in items if b.get("id") == state["bot_id"]]
    assert hit, "bots 列表应含新 bot"
