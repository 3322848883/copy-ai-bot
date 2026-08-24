# TradeTracker（M3 T3.7：仓位快照 + 对账 + PnL）
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.exchange_clients.registry import get_adapter
from api.models.bot import CopyBot, PositionSnapshot
from api.models.user import ApiKey

logger = logging.getLogger("signal-saas.tradetracker")


class TradeTracker:
    """跟踪机器人持仓：对账交易所实仓 → PositionSnapshot → 收益快照。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def reconcile_position(self, bot: CopyBot, symbol: str) -> dict | None:
        """对账单个仓位：交易所实仓 vs 本地快照。"""
        api_row = await self.db.get(ApiKey, bot.api_key_id)
        if api_row is None:
            return None
        from api.services.apikeyvault.service import ApiKeyVaultService

        from api.core.config import get_settings

        plain = ApiKeyVaultService(get_settings().vault_key_hex).decrypt(
            api_row.ciphertext, api_row.nonce, api_row.tag, api_row.aad
        )
        parts = plain.split("\n", 1)
        api_key_plain = parts[0]
        secret = parts[1] if len(parts) > 1 else ""
        adapter = get_adapter(bot.exchange)
        remote = await adapter.get_position(symbol, api_key_plain, secret)
        if remote is None:
            # 交易所无仓位 → 本地快照关闭
            local = (
                await self.db.execute(
                    select(PositionSnapshot).where(
                        PositionSnapshot.bot_id == bot.id,
                        PositionSnapshot.symbol == symbol,
                        PositionSnapshot.is_open == True,  # noqa: E712
                    )
                )
            ).scalars().first()
            if local:
                local.is_open = False
                await self.db.commit()
            return None
        return remote

    async def snapshot_pnl(self, bot: CopyBot) -> dict:
        """汇总机器人的未实现/已实现 PnL 快照。"""
        rows = (
            await self.db.execute(
                select(PositionSnapshot).where(
                    PositionSnapshot.bot_id == bot.id,
                    PositionSnapshot.is_open == True,  # noqa: E712
                )
            )
        ).scalars().all()

        total_unrealized = 0.0
        total_notional = 0.0
        for r in rows:
            total_unrealized += r.unrealized_pnl
            total_notional += r.notional_usdt

        # 已实现 PnL：减仓/平仓时累计到 realized_pnl（open+closed 全部快照求和）。
        # ★ 2026-08-24：此前以 SUM(unrealized_pnl) WHERE is_open=False 兜底，
        #   而 mark_price 从不刷新 unrealized_pnl 恒为 0 → 已实现盈亏恒为 0。
        realized = await self.db.scalar(
            select(func.coalesce(func.sum(PositionSnapshot.realized_pnl), 0.0)).where(
                PositionSnapshot.bot_id == bot.id,
            )
        )
        return {
            "bot_id": bot.id,
            "open_positions": len(rows),
            "total_notional_usdt": round(total_notional, 2),
            "unrealized_pnl_usdt": round(total_unrealized, 2),
            "realized_pnl_usdt": round(float(realized or 0), 2),
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        }
