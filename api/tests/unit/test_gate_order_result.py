from __future__ import annotations

import asyncio

from api.exchange_clients.gate import GateAdapter


def run(coro):
    return asyncio.run(coro)


def _adapter_with_response(response: dict) -> GateAdapter:
    adapter = GateAdapter()
    adapter.mock = False

    async def fake_post(*args, **kwargs):
        return response

    adapter._signed_post = fake_post
    return adapter


def test_finished_ioc_without_fill_is_cancelled():
    adapter = _adapter_with_response({
        "id": "1", "status": "finished", "finish_as": "ioc",
        "size": 10, "left": 10, "fill_size": 0, "fill_price": "0",
    })
    result = run(adapter.place_order(
        symbol="BTCUSDT", side="buy", qty=10, leverage=2,
        margin_mode="isolated", reduce_only=False, api_key="k", api_secret="s",
        price=100,
    ))
    assert result.status == "cancelled"
    assert result.filled_qty == 0


def test_finished_order_uses_actual_fill_size():
    adapter = _adapter_with_response({
        "id": "2", "status": "finished", "finish_as": "filled",
        "size": 10, "left": 6, "fill_size": 4, "fill_price": "101.5",
    })
    result = run(adapter.place_order(
        symbol="BTCUSDT", side="buy", qty=10, leverage=2,
        margin_mode="isolated", reduce_only=False, api_key="k", api_secret="s",
        price=102,
    ))
    assert result.status == "filled"
    assert result.filled_qty == 4
    assert result.avg_price == 101.5


def test_permission_check_rejects_read_only_futures_key():
    adapter = GateAdapter()
    adapter.mock = False

    async def fake_get(path, api_key, api_secret, query=""):
        assert path == "/account/main_keys"
        return [{
            "state": 1, "key": "abc***",
            "perms": [{"name": "futures", "read_only": True}],
        }]

    adapter._signed_get = fake_get
    perms = run(adapter.check_permissions("abcdef", "secret"))
    assert perms == {"read": True, "trade": False, "withdraw": False}


def test_permission_check_accepts_active_futures_write_key():
    adapter = GateAdapter()
    adapter.mock = False

    async def fake_get(path, api_key, api_secret, query=""):
        return [{
            "state": 1, "key": "abc***",
            "perms": [{"name": "futures", "read_only": False}],
        }]

    adapter._signed_get = fake_get
    perms = run(adapter.check_permissions("abcdef", "secret"))
    assert perms == {"read": True, "trade": True, "withdraw": False}


def test_client_order_id_is_sent_as_gate_text():
    adapter = GateAdapter()
    adapter.mock = False
    captured = {}

    async def fake_post(path, api_key, api_secret, payload=None, query=""):
        captured.update(payload or {})
        return {
            "id": "3", "status": "finished", "finish_as": "filled",
            "size": 2, "left": 0, "fill_size": 2, "fill_price": "100",
        }

    adapter._signed_post = fake_post
    result = run(adapter.place_order(
        symbol="BTCUSDT", side="buy", qty=2, leverage=10,
        margin_mode="isolated", reduce_only=False, api_key="k", api_secret="s",
        price=100, client_order_id="t-cp1234567890",
    ))
    assert result.status == "filled"
    assert captured["text"] == "t-cp1234567890"


def test_fetch_order_accepts_client_order_id_and_normalizes_fill():
    adapter = GateAdapter()
    adapter.mock = False

    async def fake_get(path, api_key, api_secret, query=""):
        assert path == "/futures/usdt/orders/t-cp123"
        return {
            "id": "99", "status": "finished", "finish_as": "filled",
            "size": -5, "left": 2, "fill_price": "126.18",
        }

    adapter._signed_get = fake_get
    result = run(adapter.fetch_order("t-cp123", "key", "secret"))
    assert result is not None
    assert result.status == "filled"
    assert result.order_id == "99"
    assert result.filled_qty == 3
    assert result.avg_price == 126.18
