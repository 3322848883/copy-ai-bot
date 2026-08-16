# 每日画像同步 00:00-05:00（M2 T2.7）
from __future__ import annotations

import logging

from api.core.config import get_settings
from api.workers.celery_app import celery_app

logger = logging.getLogger("signal-saas.workers.profile")

# 连续失败告警阈值（★ T2.7：连续 3 天失败告警）
PROFILE_FAIL_ALERT_KEY = "profile:consecutive_fail_days"
PROFILE_FAIL_MAX = 3


async def run_sync_daily(limit: int = 50) -> int:
    """画像同步核心（async）：全量带单员 → TraderProfile 快照。

    ★ G05：7d/30d/90d/累计 ROI + win_rate_all + trading_days。
    """
    from api.db.session import get_session_factory
    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalstore.service import SignalStore
    from api.workers.tasks_signal import _save_profile

    factory = get_session_factory()
    async with factory() as db:
        store = SignalStore(db)
        scraper = GateScraper()
        traders = await scraper.fetch_top_traders(limit=limit)
        count = 0
        for trader in traders:
            await store.upsert_trader("gate", trader.trader_id, trader.name)
            await _save_profile(store, trader)
            count += 1
        await db.commit()
        _mark_success()
    return count


def run_sync_one_sync(trader_id: str) -> dict:
    """同步单个带单员画像（后台「同步画像」手动触发，同步执行）。"""
    import asyncio

    from api.db.session import get_session_factory
    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalstore.service import SignalStore
    from api.workers.tasks_signal import _save_profile

    async def _one() -> dict:
        factory = get_session_factory()
        async with factory() as db:
            store = SignalStore(db)
            scraper = GateScraper()
            leader = await scraper.get_leader_by_id(trader_id)
            if leader is None:
                return {"trader_id": trader_id, "updated": False, "reason": "未找到该带单员"}
            await store.upsert_trader("gate", leader.trader_id, leader.name)
            await _save_profile(store, leader)
            await db.commit()
            return {"trader_id": trader_id, "updated": True, "name": leader.name}

    try:
        return asyncio.run(_one())
    except Exception as exc:  # noqa: BLE001
        logger.exception("manual profile sync failed: %s", exc)
        return {"trader_id": trader_id, "updated": False, "reason": str(exc)}


@celery_app.task(name="profile.sync_daily")
def sync_daily_profiles(exchange: str | None = None) -> int:
    """同步 TraderProfile 快照（00:00-05:00 Celery Beat 调度；dev/prod 统一真实执行）。"""
    import asyncio

    try:
        return asyncio.run(run_sync_daily())
    except Exception as exc:  # noqa: BLE001
        _mark_failure()
        logger.exception("profile sync failed: %s", exc)
        raise


def _mark_success() -> None:
    from redis import Redis

    r = Redis.from_url(get_settings().redis_url, decode_responses=True)
    r.delete(PROFILE_FAIL_ALERT_KEY)


def _mark_failure() -> None:
    from redis import Redis

    r = Redis.from_url(get_settings().redis_url, decode_responses=True)
    fails = r.incr(PROFILE_FAIL_ALERT_KEY)
    logger.error("profile sync consecutive failures: %s", fails)
    if fails >= PROFILE_FAIL_MAX:
        # ★ T2.7：连续 3 天失败 → 告警（生产接告警通道；dev 记日志）
        logger.critical(
            "ALERT: 画像同步已连续 %s 天失败，请检查数据源/代理/爬虫（signal-saas T2.7）", fails
        )
