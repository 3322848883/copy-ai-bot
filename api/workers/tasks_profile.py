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


@celery_app.task(name="profile.sync_daily")
def sync_daily_profiles(exchange: str | None = None) -> int:
    """同步 TraderProfile 快照（00:00-05:00 Celery Beat 调度）。"""
    settings = get_settings()
    if settings.app_env == "dev":
        import asyncio

        try:
            return asyncio.run(run_sync_daily())
        except Exception as exc:  # noqa: BLE001
            _mark_failure()
            logger.exception("profile sync failed: %s", exc)
            raise
    raise NotImplementedError("生产环境由独立 worker 执行（真实交易所数据源）")


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
