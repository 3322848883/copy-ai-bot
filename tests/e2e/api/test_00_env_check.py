# -*- coding: utf-8 -*-
"""stage 00 — 环境检查：healthz / openapi / 依赖探活。"""
from __future__ import annotations

import httpx


def test_healthz(api):
    resp = api.request("GET", "/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


def test_openapi_has_core_routes(api):
    resp = api.request("GET", "/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/v1/auth/register" in paths
    assert "/v1/auth/verify-email" in paths
    assert "/v1/auth/login" in paths
    assert "/v1/payments" in paths
    assert "/admin/v1/payments/{order_id}/manual" in paths
    assert "/v1/bots" in paths
    assert "/v1/withdrawals" in paths
    assert "/admin/v1/auth/login" in paths


def test_web_register_page():
    resp = httpx.get("http://localhost:3000/register", timeout=15)
    assert resp.status_code == 200


def test_mailhog_api_reachable():
    resp = httpx.get("http://localhost:8025/api/v1/messages", timeout=10)
    assert resp.status_code == 200
