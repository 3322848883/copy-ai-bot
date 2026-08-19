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


async def run_sync_one_sync(trader_id: str) -> dict:
    """同步单个带单员画像（后台「同步画像」手动触发，同步执行）。

    ★ 原生 async：FastAPI 路由（已运行的事件循环）内 asyncio.run() 会炸
      "cannot be called from a running event loop"——路由直接 await 本协程。
    """
    from api.db.session import get_session_factory
    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalstore.service import SignalStore

    factory = get_session_factory()
    async with factory() as db:
        store = SignalStore(db)
        scraper = GateScraper()
        leader = None
        # ★ detail 接口需登录态：优先复用登录会话（signal_session，用完关闭），
        #   避免 GateScraper 自建浏览器与 poll_live 争抢 data/scraper 目录锁。
        #   admin hold 生效期间：admin 浏览器占住 signal_session 目录——fetch_api 会
        #   跳过（防争抢），此时走 scraper 独立目录会撞 data/scraper 锁（poll_live 常驻）。
        #   ★ 两目录都被占时等待重试（admin 会话 900s TTL / poll_live 60s 周期释放）。
        try:
            from api.services.signal_session.service import get_signal_session

            svc = get_signal_session()
            held = svc.admin_hold_active()
            leader = None
            if not held:
                leader = await scraper.get_leader_by_id(trader_id, fetcher=svc.fetch_api)
                await svc.close()
        except Exception:  # noqa: BLE001 登录会话不可用（未登录/锁冲突）退回独立浏览器
            leader = None
            held = False
        if leader is None:
            # ★ 退回独立浏览器：poll_live（60s 周期）可能正持有 data/scraper 目录锁，
            #   重试等其释放（每次间隔 15s，最多 5 次 ≈ 75s > poll_live 周期）。
            import asyncio as _asyncio

            for attempt in range(5):
                try:
                    leader = await scraper.get_leader_by_id(trader_id)
                    break
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc)
                    if "ProcessSingleton" in msg or "SingletonLock" in msg:
                        await _asyncio.sleep(15)
                        continue
                    raise exc
        if leader is None:
            return {"trader_id": trader_id, "updated": False, "reason": "未找到该带单员"}
        # ★ get_leader_by_id 返回 dict（detail 接口无昵称字段）：用 _save_followed_profile
        #   （dict 版画像写入）；_save_profile 只接受带属性对象（RawTrader/ORM）。
        from api.workers.tasks_signal import _save_followed_profile

        trader = await store.upsert_trader("gate", str(leader.get("leader_id") or trader_id),
                                           name=leader.get("nick") or f"Leader{trader_id}")
        await _save_followed_profile(store, trader, leader)
        await db.commit()
        return {"trader_id": trader_id, "updated": True, "name": trader.name}


@celery_app.task(name="profile.sync_daily")
def sync_daily_profiles(exchange: str | None = None, limit: int | None = None) -> int:
    """同步 TraderProfile 快照（00:00-05:00 Celery Beat 调度；dev/prod 统一真实执行）。

    limit：后台「同步画像」手动触发传入（signals.py send_task kwargs）；
    Beat 定时调度不传，走 run_sync_daily 默认 50。
    """
    import asyncio

    try:
        return asyncio.run(run_sync_daily(limit=limit) if limit else run_sync_daily())
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
