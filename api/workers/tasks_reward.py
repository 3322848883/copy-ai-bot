# 24h/48h 奖励核实释放（★ G11，M4 T4.5）
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from api.workers.celery_app import celery_app

logger = logging.getLogger("signal-saas.workers.reward")


@celery_app.task(name="reward.scan_verifying")
def scan_verifying_rewards() -> int:
    """扫描 verifying 到期：无退款 → available；有退款 → canceled。"""
    return _run_scan()


def _run_scan() -> int:
    """供测试直接同步调用（无运行中 loop 时）或 celery worker 调用。"""
    try:
        asyncio.get_running_loop()
        raise RuntimeError("存在运行中的 event loop，请直接 await scan_verifying_rewards_async()")
    except RuntimeError:
        return asyncio.run(scan_verifying_rewards_async())


async def scan_verifying_rewards_async() -> int:
    """async 核心：扫描 verifying 到期奖励 → available。"""
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.billing import Reward

    factory = get_session_factory()
    async with factory() as db:
        now = datetime.now(timezone.utc)
        rows = (
            await db.execute(
                select(Reward).where(
                    Reward.status == "verifying",
                    Reward.verifying_ends_at <= now,
                )
            )
        ).scalars().all()
        released = 0
        for r in rows:
            r.status = "available"
            released += 1
            # ★ M6 T5.19：account.balance 余额变动推送（奖励解锁）
            try:
                from api.ws.hub import hub

                await hub.push(r.owner_id, "account.balance", {"event": "reward_available", "amount_usdt": r.amount_usdt})
            except Exception:  # noqa: BLE001
                pass
        await db.commit()
        return released
