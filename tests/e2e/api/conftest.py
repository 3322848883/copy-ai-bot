# -*- coding: utf-8 -*-
"""pytest 公共设施：HTTP client / admin token / state.json 共享 / 429 重试 / 限流纪律。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
import pytest

# 使 api/helpers 可被 from helpers import ... 导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE = os.environ.get("E2E_BASE", "http://localhost:8000")
ADMIN_EMAIL = "e2e_docker_admin@t.com"
ADMIN_PASS = "E2eAdmin!2026"
E2E_ROOT = Path(__file__).resolve().parents[1]  # tests/e2e/
STATE_FILE = E2E_ROOT / "state.json"

# /v1/auth/ 限流 10 次/分/IP → 用户组间 sleep 防 429
AUTH_GROUP_SLEEP = 65


class ApiClient:
    """带 429 重试与 JSON 断言的 httpx 封装。"""

    def __init__(self) -> None:
        self.client = httpx.Client(base_url=BASE, timeout=90)

    def request(self, method: str, path: str, *, token: str | None = None, **kwargs):
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        for attempt in range(4):
            resp = self.client.request(method, path, headers=headers, **kwargs)
            if resp.status_code == 429:
                retry = float(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            return resp
        return resp

    def close(self) -> None:
        self.client.close()


@pytest.fixture(scope="session")
def api():
    client = ApiClient()
    yield client
    client.close()


@pytest.fixture(scope="session")
def admin_token(api):
    resp = api.request("POST", "/admin/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert resp.status_code == 200, f"admin 登录失败: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]


def load_state() -> dict:
    if STATE_FILE.exists():
        raw = STATE_FILE.read_bytes()
        # 容错：可能带 UTF-8 BOM（Windows Set-Content -Encoding UTF8 会写 BOM）
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        return json.loads(raw.decode("utf-8"))
    return {}


def save_state(state: dict) -> None:
    # 显式无 BOM UTF-8
    STATE_FILE.write_bytes(json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"))


@pytest.fixture(scope="session")
def state():
    return load_state()


@pytest.fixture(scope="session")
def save():
    def _save(state: dict) -> None:
        save_state(state)
    return _save
