# -*- coding: utf-8 -*-
"""stage 05 — 策略：admin force 上架（G04 留痕）→ 公开列表/详情。"""
from __future__ import annotations

from conftest import load_state, save_state


def test_admin_force_list_strategy(api, admin_token, save):
    state = load_state()
    resp = api.request(
        "POST", "/admin/v1/signals",
        json={
            "trader_id": state["trader_id"],
            "display_name": "E2E测试策略",
            "style": "trend",
            "risk_rating": "mid",
            "force": True,
            "force_reason": "e2e自动化测试",
        },
        token=admin_token,
    )
    assert resp.status_code == 200, f"force 上架失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("status") == "listed"
    assert data.get("forced") is True
    assert data.get("gate_passed") is True
    state["strategy_id"] = data["id"]
    save(state)


def test_strategy_public_list(api):
    state = load_state()
    resp = api.request("GET", "/v1/strategies")
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    hit = [s for s in items if s.get("id") == state["strategy_id"]]
    assert hit, "公开策略列表应包含 E2E 策略"


def test_strategy_public_detail(api):
    state = load_state()
    resp = api.request("GET", f"/v1/strategies/{state['strategy_id']}")
    assert resp.status_code == 200, f"详情失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("display_name") == "E2E测试策略"
    # 画像字段存在（G21 画像兜底）
    assert "profile_state" in data or "roi_30d" in data or "win_rate_all" in data


def test_admin_strategy_status_pause_resume(api, admin_token):
    """下架/上架状态流转（G04 配套）。"""
    state = load_state()
    sid = state["strategy_id"]
    resp = api.request("PATCH", f"/admin/v1/signals/{sid}/status", json={"status": "paused"}, token=admin_token)
    assert resp.status_code == 200 and resp.json().get("status") == "paused"
    resp = api.request("PATCH", f"/admin/v1/signals/{sid}/status", json={"status": "listed"}, token=admin_token)
    assert resp.status_code == 200 and resp.json().get("status") == "listed"


def test_admin_strategy_gray(api, admin_token):
    state = load_state()
    resp = api.request("PATCH", f"/admin/v1/signals/{state['strategy_id']}/gray", json={"gray_pct": 30}, token=admin_token)
    assert resp.status_code == 200 and resp.json().get("gray_pct") == 30
