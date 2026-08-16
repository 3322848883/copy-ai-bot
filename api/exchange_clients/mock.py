# dev mock 适配器基类（M3 T3.0：生产切换官方实现前，5 家统一 mock 行为）
from __future__ import annotations

from typing import Any

from api.exchange_clients.base import BalanceItem, ExchangeAdapter, OrderResult


class MockAdapterMixin(ExchangeAdapter):
    """dev 环境 mock 实现：验证全链路（绑定校验/下单/持仓）无需真实交易所。"""

    async def test_connect(self, api_key: str, api_secret: str) -> bool:
        return bool(api_key and api_secret)

    async def fetch_balance(self, api_key: str, api_secret: str) -> list[BalanceItem]:
        return [BalanceItem(asset="USDT", free=1000.0, locked=0.0)]

    async def check_permissions(self, api_key: str, api_secret: str) -> dict[str, bool]:
        return {"read": True, "trade": True, "withdraw": False}

    async def set_leverage(self, symbol: str, leverage: int, api_key: str, api_secret: str) -> None:
        return None

    async def set_margin_mode(self, symbol: str, mode: str, leverage: int, api_key: str, api_secret: str) -> None:
        return None

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
        price: float | None = None,
    ) -> OrderResult:
        return OrderResult(
            order_id=f"mock-{self.exchange}-{symbol}-{side}-{qty}",
            status="filled",
            filled_qty=qty,
            avg_price=price or 100.0,
            raw={"mock": True, "exchange": self.exchange},
        )

    async def get_position(self, symbol: str, api_key: str, api_secret: str) -> dict[str, Any] | None:
        return {"symbol": symbol, "size": 0.5, "entry_price": 96000.0, "mark_price": 96500.0, "unrealised_pnl": 250.0}

    async def fetch_contract_spec(self, symbol: str) -> dict[str, Any]:
        return {"face_value_usdt": 1.0, "min_size": 0.1, "size_precision": 3}
