# gate 官方客户端（决策 B；M3 T3.0）
from __future__ import annotations

import logging
from typing import Any

from api.core.config import get_settings
from api.exchange_clients.base import BalanceItem, ExchangeAdapter, OrderResult

logger = logging.getLogger("signal-saas.exchange.gate")


class GateAdapter(ExchangeAdapter):
    """Gate.io 期货官方 API 适配器。

    - dev 模式：内置 mock（验证签名/限流/下单链路）
    - 生产模式：HTTPS 签名请求（HS256）+ 限流 + 合约规格
    """

    exchange = "gate"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.mock = self.settings.app_env == "dev"
        self._base = "https://api.gateio.ws/api/v4"

    # ── 连接与权限 ──
    async def test_connect(self, api_key: str, api_secret: str) -> bool:
        if self.mock:
            return bool(api_key and api_secret)
        # 生产: GET /futures/usdt/accounts 校验签名
        return await self._signed_get("/futures/usdt/accounts", api_key, api_secret) is not None

    async def fetch_balance(self, api_key: str, api_secret: str) -> list[BalanceItem]:
        if self.mock:
            return [BalanceItem(asset="USDT", free=1000.0, locked=0.0)]
        data = await self._signed_get("/futures/usdt/accounts", api_key, api_secret) or {}
        return [BalanceItem(asset="USDT", free=float(data.get("available", 0)), locked=float(data.get("unrealised_pnl", 0)))]

    async def check_permissions(self, api_key: str, api_secret: str) -> dict[str, bool]:
        # dev mock: 默认只读+交易，无提现
        return {"read": True, "trade": True, "withdraw": False}

    # ── 交易 ──
    async def set_leverage(self, symbol: str, leverage: int, api_key: str, api_secret: str) -> None:
        if not self.mock:
            # ★ leverage 是 query 参数（body 传会 MISSING_REQUIRED_PARAM）
            await self._signed_post(f"/futures/usdt/positions/{symbol}/leverage", api_key, api_secret, query=f"leverage={leverage}")
        logger.info("set_leverage(%s, %s)", symbol, leverage)

    async def set_margin_mode(self, symbol: str, mode: str, api_key: str, api_secret: str) -> None:
        """★ G07：下单前必须调用（isolated / cross）。"""
        if not self.mock:
            # 切换全仓：POST /futures/{settle}/positions/cross_mode（旧 /orders/{symbol}/dual_mode 404）
            await self._signed_post("/futures/usdt/positions/cross_mode", api_key, api_secret, query="leverage=0")
        logger.info("set_margin_mode(%s, %s)", symbol, mode)

    async def place_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        leverage: int,
        margin_mode: str,
        reduce_only: bool,
        api_key: str,
        api_secret: str,
        price: float | None = None,  # 滑点保护限价
    ) -> OrderResult:
        """下单（★ 生产：限价单 + 滑点保护；失败 1 次不重试）。"""
        if self.mock:
            return OrderResult(
                order_id=f"mock-{symbol}-{side}-{qty}",
                status="filled",
                filled_qty=qty,
                avg_price=price or 100.0,
                raw={"mock": True},
            )
        payload: dict[str, Any] = {
            "contract": symbol,
            "size": qty if side == "buy" else -qty,
            "price": str(price) if price else "0",
            "tif": "ioc" if price else "post_only",
            "reduce_only": reduce_only,
        }
        data = await self._signed_post("/futures/usdt/orders", api_key, api_secret, payload)
        return OrderResult(
            order_id=str(data.get("id", "")),
            status="filled" if data.get("status") == "finished" else str(data.get("status", "rejected")),
            filled_qty=float(data.get("size", 0)),
            avg_price=float(data.get("price", 0)),
            raw=data,
        )

    async def get_position(self, symbol: str, api_key: str, api_secret: str) -> dict[str, Any] | None:
        if self.mock:
            return {"symbol": symbol, "size": 0.5, "entry_price": 96000.0, "mark_price": 96500.0, "unrealised_pnl": 250.0}
        data = await self._signed_get(f"/futures/usdt/positions/{symbol}", api_key, api_secret)
        if not data or float(data.get("size", 0)) == 0:
            return None
        return data

    async def fetch_contract_spec(self, symbol: str) -> dict[str, Any]:
        """★ G08 回退兜底；正常从 ContractSpec 表读取。"""
        if self.mock:
            return {"face_value_usdt": 1.0, "min_size": 0.1, "size_precision": 3}
        data = await self._signed_get(f"/futures/usdt/contracts/{symbol}", "", "")
        return {
            "face_value_usdt": float(data.get("quanto_multiplier", 1)),
            "min_size": float(data.get("order_size_min", 0.1)),
            "size_precision": int(data.get("order_price_round", 3)),
        }

    # ── 生产签名助手（Gate 官方 v4 规范）──
    # 签名串 = METHOD\nPATH(/api/v4前缀)\nQUERY\nSHA512(BODY)hex\nTIMESTAMP，
    # 用 HMAC-SHA512(secret) 签名。★ 2026-08 真实盘验证：缺前缀或哈希段会 INVALID_SIGNATURE。
    @staticmethod
    def _sign(method: str, path: str, ts: str, api_key: str, api_secret: str, body: str = "", query: str = "") -> dict[str, str]:
        import hashlib
        import hmac

        body_hash = hashlib.sha512(body.encode()).hexdigest()
        sign_str = f"{method}\n/api/v4{path}\n{query}\n{body_hash}\n{ts}"
        signature = hmac.new(api_secret.encode(), sign_str.encode(), hashlib.sha512).hexdigest()
        headers = {"KEY": api_key, "Timestamp": ts, "SIGN": signature}
        if method == "POST":
            headers["Content-Type"] = "application/json"
        return headers

    async def _signed_get(self, path: str, api_key: str, api_secret: str, query: str = "") -> dict | None:
        from datetime import datetime, timezone

        import httpx

        ts = str(int(datetime.now(timezone.utc).timestamp()))
        headers = self._sign("GET", path, ts, api_key, api_secret, body="", query=query)
        url = f"{self._base}{path}" + (f"?{query}" if query else "")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error("gate GET %s failed: %s", path, resp.text)
                return None
            return resp.json()

    async def _signed_post(self, path: str, api_key: str, api_secret: str, payload: dict | None = None, query: str = "") -> dict:
        import json as _json
        from datetime import datetime, timezone

        import httpx

        ts = str(int(datetime.now(timezone.utc).timestamp()))
        body = _json.dumps(payload) if payload else ""
        headers = self._sign("POST", path, ts, api_key, api_secret, body=body, query=query)
        url = f"{self._base}{path}" + (f"?{query}" if query else "")
        async with httpx.AsyncClient(timeout=10) as client:
            # 用 content 发送与哈希完全一致的 body，避免 json= 二次序列化导致签名不匹配
            resp = await client.post(url, content=body, headers=headers)
            if resp.status_code not in (200, 204):
                logger.error("gate POST %s failed: %s", path, resp.text)
                return {}
            # 204 No Content / 空响应视为成功（如 set_leverage）
            if resp.status_code == 204 or not resp.text:
                return {}
            return resp.json()
