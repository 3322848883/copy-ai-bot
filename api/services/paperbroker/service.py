# PaperBroker（M6 T6.2：沙箱模拟盘，不触达真实交易所）
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.bot import PositionSnapshot
from api.services.executor.service import ExecResult

logger = logging.getLogger("signal-saas.paper")

PAPER_START_BALANCE = 10_000.0  # 虚拟起始余额 USDT
PAPER_DEFAULT_PRICE = 50_000.0  # 信号价缺失时的撮合价


class PaperBroker:
    """模拟盘撮合：按信号价成交，持仓/余额经 PositionSnapshot 持久化。

    与真实链路共用 _sync_position 记账，风控/灰度/订阅拦截完全一致，
    仅跳过 ExchangeAdapter 网络调用（T6.2 沙箱目标）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_free_balance(self, bot_id: int) -> float:
        """虚拟余额 = 起始余额 - 已锁定名义（从快照推导）。"""
        total_locked = sum(await self._locked_list(bot_id))
        return round(PAPER_START_BALANCE - total_locked, 2)

    async def _locked_list(self, bot_id: int) -> list[float]:
        rows = (
            await self.db.execute(
                select(PositionSnapshot.notional_usdt).where(
                    PositionSnapshot.bot_id == bot_id,
                    PositionSnapshot.is_open == True,  # noqa: E712
                )
            )
        ).scalars().all()
        return [float(x or 0) for x in rows]

    async def get_position(self, bot_id: int, symbol: str) -> dict | None:
        """从 PositionSnapshot 读取虚拟持仓（对齐 adapter.get_position 输出）。"""
        row = (
            await self.db.execute(
                select(PositionSnapshot).where(
                    PositionSnapshot.bot_id == bot_id,
                    PositionSnapshot.symbol == symbol,
                    PositionSnapshot.is_open == True,  # noqa: E712
                )
            )
        ).scalars().first()
        if row is None:
            return None
        return {
            "qty": row.qty,
            "side": row.side,
            "entry_price": row.entry_price,
            "mark_price": row.mark_price,
            "unrealized_pnl": row.unrealized_pnl,
        }

    async def execute(
        self,
        *,
        bot,
        symbol: str,
        side: str,
        qty: float,
        leverage: int,
        margin_mode: str,
        reduce_only: bool,
        signal_price: float | None,
    ) -> ExecResult:
        """模拟成交：signal_price 或默认价；立即全量成交。"""
        price = signal_price if signal_price and signal_price > 0 else PAPER_DEFAULT_PRICE
        logger.info(
            "paper fill bot=%s %s %s qty=%s @ %s (reduce_only=%s)",
            bot.id, symbol, side, qty, price, reduce_only,
        )
        return ExecResult(
            success=True,
            order_id=f"paper-{bot.id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            filled_qty=qty,
            avg_price=round(price, 6),
            latency_ms=1,
        )
