# PaperBroker（M6 T6.2：沙箱模拟盘，不触达真实交易所）
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.bot import CopyBot, PositionSnapshot
from api.services.executor.service import ExecResult
from api.services.prices import fetch_futures_price

logger = logging.getLogger("signal-saas.paper")

PAPER_START_BALANCE = 10_000.0  # 虚拟起始余额 USDT
PAPER_DEFAULT_PRICE = 50_000.0  # 行情获取失败时的兜底撮合价


class PaperBroker:
    """模拟盘撮合：按真实行情价成交，持仓/余额经 PositionSnapshot 持久化。

    与真实链路共用 _sync_position 记账，风控/灰度/订阅拦截完全一致，
    仅跳过 ExchangeAdapter 网络调用（T6.2 沙箱目标）。
    ★ 2026-08-24：成交价改用 Gate 公开行情实时价（此前固定 50_000 导致
      所有模拟盘盈亏失真）；mark_price 由 WS 实时通道 + REST 兜底任务刷新。
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
        """模拟成交：真实行情价（信号价优先 → Gate 公开 ticker → 兜底默认价）；立即全量成交。"""
        price = signal_price if signal_price and signal_price > 0 else None
        if not price:
            price = await fetch_futures_price(symbol)
        if not price or price <= 0:
            price = PAPER_DEFAULT_PRICE
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

    async def update_marks(self, prices: dict[str, float]) -> int:
        """用最新价刷新全部模拟盘持仓的 mark_price + 未实现盈亏。

        prices 键为快照内存储的 symbol（无下划线，如 GUAUSDT）。
        返回更新条数；WS 实时通道与 REST 兜底任务共用。
        """
        rows = (
            await self.db.execute(
                select(PositionSnapshot)
                .join(CopyBot, CopyBot.id == PositionSnapshot.bot_id)
                .where(
                    CopyBot.paper == True,  # noqa: E712
                    PositionSnapshot.is_open == True,  # noqa: E712
                )
            )
        ).scalars().all()
        updated = 0
        for r in rows:
            price = prices.get(r.symbol)
            if not price or price <= 0:
                continue
            r.mark_price = price
            entry = r.entry_price or price
            side_sign = 1.0 if (r.side or "long") == "long" else -1.0
            # ★ 2026-08-24：face 直接读快照 face_value（_sync_position 落库时写入）。
            #   此前用 notional/qty 推导得到 face×price，盈亏虚大 1/face=1 万倍。
            face = r.face_value or 1.0
            r.unrealized_pnl = (price - entry) * r.qty * face * side_sign
            updated += 1
        if updated:
            await self.db.commit()
        return updated
