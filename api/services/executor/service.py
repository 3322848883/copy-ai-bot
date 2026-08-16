# OrderRouter（M3 T3.6：官方直连 + 滑点保护 + T3.8 失败归因 8 类）
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from api.exchange_clients.registry import get_adapter

logger = logging.getLogger("signal-saas.executor")

# ★ 失败归因 8 类（T3.8；CopyOrder.failure_category）
FAILURE_CATEGORIES = (
    "balance", "permission", "leverage", "symbol",
    "min_size", "network", "price_deviation", "slippage", "other",
)


@dataclass
class ExecResult:
    success: bool
    failure_category: str | None = None
    reason: str = ""
    order_id: str | None = None
    filled_qty: float = 0.0
    avg_price: float = 0.0
    latency_ms: int = 0


class OrderRouter:
    """执行路由：ExchangeAdapter 直连下单。

    - ★ 滑点保护：限价 = 信号价 × (1 ± slippage_bps/1e4)；偏离超限拒绝
    - 失败 1 次不重试（设计蓝本 §6.3）
    - 失败归因 8 类贯穿（balance/permission/leverage/symbol/min_size/network/price_deviation/slippage/other）
    """

    def __init__(self, slippage_bps: int = 50) -> None:
        """slippage_bps 默认 50 = 0.5% 滑点保护。"""
        self.slippage_bps = slippage_bps

    async def execute(
        self,
        *,
        exchange: str,
        symbol: str,
        side: str,                 # buy / sell
        qty: float,
        leverage: int,
        margin_mode: str,          # isolated / cross（★ G07）
        reduce_only: bool,
        signal_price: float | None,
        api_key: str,
        api_secret: str,
    ) -> ExecResult:
        """执行下单。signal_price=None 表示市价（mock 允许）。"""
        start = datetime.now(timezone.utc)
        try:
            adapter = get_adapter(exchange)
        except ValueError:
            return ExecResult(False, "symbol", f"adapter 未注册: {exchange}")

        # ★ 滑点保护：限价 = 信号价 × (1 ± bps/1e4)
        limit_price = None
        if signal_price and signal_price > 0:
            factor = 1 + (self.slippage_bps / 10_000) * (1 if side == "buy" else -1)
            limit_price = round(signal_price * factor, 6)

        # ★ G07：下单前 set_margin_mode + set_leverage
        try:
            await adapter.set_margin_mode(symbol, margin_mode, leverage, api_key, api_secret)
            await adapter.set_leverage(symbol, leverage, api_key, api_secret)
        except Exception as exc:  # noqa: BLE001
            return ExecResult(False, "leverage", f"设置杠杆/保证金模式失败: {exc}")

        # 下单（失败 1 次不重试）
        try:
            result = await adapter.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                leverage=leverage,
                margin_mode=margin_mode,
                reduce_only=reduce_only,
                api_key=api_key,
                api_secret=api_secret,
                price=limit_price,
            )
        except Exception as exc:  # noqa: BLE001
            category = self._classify_error(str(exc))
            return ExecResult(False, category, str(exc))

        latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        if result.status == "filled":
            return ExecResult(
                True,
                order_id=result.order_id,
                filled_qty=result.filled_qty,
                avg_price=result.avg_price,
                latency_ms=latency,
            )
        return ExecResult(
            False, "other", f"order rejected: {result.status}",
            order_id=result.order_id, latency_ms=latency,
        )

    def _classify_error(self, msg: str) -> str:
        msg_l = msg.lower()
        rules = [
            ("balance", ("balance", "insufficient", "margin")),
            ("permission", ("permission", "forbidden", "denied", "api key")),
            ("leverage", ("leverage", "leverage_set")),
            ("symbol", ("symbol", "contract", "instrument")),
            ("min_size", ("min size", "too small", "minimum")),
            ("network", ("network", "timeout", "connect", "econnreset")),
            ("price_deviation", ("price", "deviation", "limit")),
            ("slippage", ("slippage", "slippage_protection")),
        ]
        for cat, kws in rules:
            if any(k in msg_l for k in kws):
                return cat
        return "other"
