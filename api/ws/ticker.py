# pnl.tick 周期推送任务（M6 P0：首页实时盈亏跳动）
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import func, select

from api.db.session import get_session_factory
from api.models.bot import CopyBot, PositionSnapshot
from api.ws.hub import hub

logger = logging.getLogger("signal-saas.ws.ticker")

TICK_INTERVAL = 8  # 秒，与蓝本 WS 模拟节奏一致


async def _snapshot_for_user(user_id: int) -> dict:
    """聚合用户全部机器人的未实现盈亏（首页 pnl.tick 负载）。"""
    factory = get_session_factory()
    async with factory() as db:
        bots = (
            await db.execute(select(CopyBot).where(CopyBot.user_id == user_id))
        ).scalars().all()
        if not bots:
            return {"bots": [], "total_unrealized_pnl_usdt": 0.0}
        bot_ids = [b.id for b in bots]
        rows = (
            await db.execute(
                select(
                    PositionSnapshot.bot_id,
                    PositionSnapshot.symbol,
                    PositionSnapshot.side,
                    PositionSnapshot.qty,
                    PositionSnapshot.mark_price,
                    PositionSnapshot.unrealized_pnl,
                    PositionSnapshot.notional_usdt,
                ).where(
                    PositionSnapshot.bot_id.in_(bot_ids),
                    PositionSnapshot.is_open == True,  # noqa: E712
                )
            )
        ).all()
        per_bot: dict[int, list[dict]] = {}
        total = 0.0
        for r in rows:
            per_bot.setdefault(r.bot_id, []).append(
                {
                    "symbol": r.symbol,
                    "side": r.side,
                    "qty": r.qty,
                    "mark_price": r.mark_price,
                    "unrealized_pnl": r.unrealized_pnl,
                    "notional_usdt": r.notional_usdt,
                }
            )
            total += r.unrealized_pnl or 0.0
        return {
            "bots": [
                {"bot_id": bid, "positions": pos, "unrealized_pnl_usdt": round(sum(p["unrealized_pnl"] or 0 for p in pos), 2)}
                for bid, pos in per_bot.items()
            ],
            "total_unrealized_pnl_usdt": round(total, 2),
        }


async def _ticker_loop() -> None:
    while True:
        try:
            for user_id in hub.online_user_ids():
                payload = await _snapshot_for_user(user_id)
                await hub.push(user_id, "pnl.tick", payload)
        except Exception:  # noqa: BLE001 单轮失败不中断
            logger.exception("pnl.tick push round failed")
        await asyncio.sleep(TICK_INTERVAL)


async def start_ticker() -> asyncio.Task:
    task = asyncio.create_task(_ticker_loop(), name="pnl-ticker")
    return task
