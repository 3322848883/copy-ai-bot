"""ExchangeAdapter 抽象（决策 B：5 家官方直连，统一接口）。

被 executor（下单）与 tradetracker（对账）调用。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class OrderResult:
    order_id: str
    status: str          # filled / rejected / cancelled
    filled_qty: float
    avg_price: float
    raw: dict[str, Any]


@dataclass
class BalanceItem:
    asset: str
    free: float
    locked: float


class ExchangeAdapter(ABC):
    """交易所官方 API 适配器基类。"""

    exchange: str = ""

    # ── 连接与权限校验 ──
    @abstractmethod
    async def test_connect(self, api_key: str, api_secret: str) -> bool: ...

    @abstractmethod
    async def fetch_balance(self, api_key: str, api_secret: str) -> list[BalanceItem]: ...

    @abstractmethod
    async def check_permissions(self, api_key: str, api_secret: str) -> dict[str, bool]:
        """返回 {read, trade, withdraw}；withdraw=True 必须拒绝绑定。"""

    # ── 交易 ──
    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int, api_key: str, api_secret: str) -> None: ...

    @abstractmethod
    async def set_margin_mode(self, symbol: str, mode: str, api_key: str, api_secret: str) -> None: ...
    # ★ G07：下单前必须调用 set_margin_mode + set_leverage

    @abstractmethod
    async def place_order(
        self,
        *,
        symbol: str,
        side: str,          # buy / sell
        qty: float,
        leverage: int,
        margin_mode: str,
        reduce_only: bool,
        api_key: str,
        api_secret: str,
    ) -> OrderResult: ...

    @abstractmethod
    async def get_position(self, symbol: str, api_key: str, api_secret: str) -> dict[str, Any] | None: ...

    # ── 合约规格（★ G08 回退兜底；正常从 ContractSpec 表读取）──
    @abstractmethod
    async def fetch_contract_spec(self, symbol: str) -> dict[str, Any]:
        """返回 {face_value_usdt, min_size, size_precision}。"""
