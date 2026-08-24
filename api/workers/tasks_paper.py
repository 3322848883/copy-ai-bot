# 模拟盘 mark_price REST 兜底刷新（WS 实时通道断线时的保险）
from __future__ import annotations

import logging

from api.workers.celery_app import celery_app

logger = logging.getLogger("signal-saas.workers.paper")


async def run_update_marks() -> dict[str, int]:
    """REST 拉取全部模拟盘持仓最新价并刷新 mark_price/未实现盈亏。"""
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.bot import CopyBot, PositionSnapshot
    from api.services.paperbroker.service import PaperBroker
    from api.services.prices import fetch_futures_prices

    factory = get_session_factory()
    async with factory() as db:
        symbols = (
            await db.execute(
                select(PositionSnapshot.symbol)
                .join(CopyBot, CopyBot.id == PositionSnapshot.bot_id)
                .where(
                    CopyBot.paper == True,  # noqa: E712
                    PositionSnapshot.is_open == True,  # noqa: E712
                )
            )
        ).scalars().all()
        symbols = list({s for s in symbols})
        if not symbols:
            return {"symbols": 0, "updated": 0}
        prices = await fetch_futures_prices(symbols)
        updated = await PaperBroker(db).update_marks(prices)
        return {"symbols": len(symbols), "updated": updated}


@celery_app.task(name="paper.update_marks")
def update_marks() -> dict[str, int]:
    import asyncio

    return asyncio.run(run_update_marks())
