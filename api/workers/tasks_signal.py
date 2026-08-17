# 定时爬虫采集（M2 T2.1 调度 + T2.7 画像同步）
from __future__ import annotations

import logging
from datetime import date

from api.core.config import get_settings
from api.workers.celery_app import celery_app

logger = logging.getLogger("signal-saas.workers.signal")


def _is_test_symbol(symbol: str) -> bool:
    """★ 测试符号兜底过滤：symbol 含 signal_test_symbols 任一标记即丢弃。"""
    settings = get_settings()
    up = symbol.upper()
    return any(mark in up for mark in settings.signal_test_symbols)


async def run_scrape_all(limit: int = 8) -> dict[str, int]:
    """采集核心（async）：排行榜 → 持仓 → 标准化 → 入库 → 画像快照。

    dev 环境用 mock 数据跑通全链路；生产接入 Playwright 适配器。
    """
    from api.db.session import get_session_factory
    from api.services.normalizer.service import SignalNormalizer
    from api.services.scraper.service import ScraperService
    from api.services.signalstore.service import SignalStore

    stats: dict[str, int] = {}
    factory = get_session_factory()
    async with factory() as db:
        store = SignalStore(db)
        scraper = ScraperService(normalizer=SignalNormalizer())
        async for trader, positions in scraper.gate.scrape_all_traders(limit=limit):
            await store.upsert_trader("gate", trader.trader_id, trader.name, trader.followers)
            for pos in positions:
                ns = scraper._to_signal(trader, pos)
                if ns is None:
                    continue
                await store.ingest(ns)
                stats["signals"] = stats.get("signals", 0) + 1
            # 画像快照（T2.7 ★G05）
            await _save_profile(store, trader)
        await db.commit()
    return stats


@celery_app.task(name="signal.scrape_all")
def scrape_all_exchanges() -> str:
    """触发 5 家交易所公开带单广场采集（模式 A，M2 T2.1）。"""
    import asyncio

    return f"scraped gate: {asyncio.run(run_scrape_all())}"


# ── ★ 实时信号轮询（只执行新开仓/新平仓，存量持仓仅作基线）──
@celery_app.task(name="signal.poll_live")
def poll_live_signals() -> str:
    """高频轮询：在单次任务内按 signal_poll_interval 连续轮询。

    - 任务连续运行 signal_poll_loop_seconds 秒，期间每 signal_poll_interval 秒轮询一轮
    - ★ 单个 GateScraper/单个 feed 跨轮复用（浏览器会话只启动/关闭一次），避免每轮新建浏览器
    - 到点返回，由 celery beat 重新踢起（避免 beat 1 秒级调度开销）
    - Redis 保存每个带单员上次持仓快照，差分产出 open/close
    - 首次轮询仅建立基线，不产出信号（存量持仓不执行）
    """
    import asyncio

    return asyncio.run(_poll_live_loop())


async def _poll_live_loop() -> str:
    """轮询主循环：按配置间隔连续跑，到 loop_seconds 返回。"""
    import asyncio
    import time

    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalfeed.service import IncrementalFeedService

    settings = get_settings()
    interval = max(settings.signal_poll_interval, 1)
    loop_seconds = max(settings.signal_poll_loop_seconds, interval + 1)
    # ★ 单个 scraper + 单个 feed：浏览器会话跨轮复用，任务结束时统一关闭
    scraper = GateScraper()
    feed = IncrementalFeedService(scraper=scraper)
    deadline = time.time() + loop_seconds
    rounds = 0
    events_total = 0
    # ★ 完全自动：每 60s 把「我账户跟单的交易员」同步为策略广场展示项
    last_sync = 0.0
    SYNC_INTERVAL = 60.0
    try:
        while time.time() < deadline:
            try:
                events_total += await _poll_live_round(feed)
            except Exception as exc:  # noqa: BLE001 单轮失败不中断循环
                logger.error("signal.poll_live 单轮失败: %s", exc)
            rounds += 1
            if time.time() - last_sync >= SYNC_INTERVAL:
                try:
                    await sync_followed_leaders(scraper=scraper)
                    last_sync = time.time()
                except Exception as exc:  # noqa: BLE001 同步失败不中断轮询
                    logger.warning("sync_followed_leaders 失败: %s", exc)
            await asyncio.sleep(interval)
    finally:
        await scraper.close()  # 释放公开爬虫浏览器
        # ★ 释放登录会话浏览器：signal_session 全局单例，_page 绑定首次 asyncio.run 的事件循环；
        #   跨任务用新 loop 复用旧 _page 会报 'NoneType' object has no attribute 'send'。
        #   本任务内关闭，登录态落盘 user_data_dir，下个任务自动重新拉起。
        try:
            from api.services.signal_session.service import get_signal_session

            await get_signal_session().close()
        except Exception as exc:  # noqa: BLE001 关闭失败不阻断
            logger.warning("signal_session close fail: %s", exc)
        # ★ 释放异步引擎连接池：asyncio.run 每次新建事件循环，跨循环复用连接会 Event loop is closed
        from api.db.session import get_engine

        await get_engine().dispose()
    return f"rounds={rounds}, events={events_total} (interval={interval}s)"


async def _poll_live_round(feed) -> int:
    """单轮轮询：查活跃机器人 → 按模式对每个带单员做持仓差分 → 产出信号。

    ★ 模式路由：leader_id ∈ signal_follower_leader_ids → 模式2（跟单账户镜像，走 follower 差分）；
       否则 → 模式1（公开广场，走 leader 差分）。二者互不混淆。
    ★ 模式2 自动发现：已跟单交易员（含空仓的）由 fetch_followed_leaders 动态发现并入监控，
       避免手动维护 signal_follower_leader_ids 漏掉新跟单交易员。
    """
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.bot import CopyBot
    from api.models.signal import Strategy, Trader

    factory = get_session_factory()
    total = 0
    async with factory() as db:
        leader_ids = (
            (
                await db.execute(
                    select(Trader.trader_id)
                    .join(Strategy, Strategy.trader_id == Trader.id)
                    .join(CopyBot, CopyBot.strategy_id == Strategy.id)
                    .where(CopyBot.status == "active")
                )
            )
            .scalars()
            .all()
        )
        if not leader_ids:
            return 0
        follower_ids = set(get_settings().signal_follower_leader_ids)
        # ★ 模式2 自动发现：合并运行中已跟单交易员（含空仓），确保不漏跟单。
        #   ★ 仅当配置为空时才每轮尝试（避免每秒调用登录会话接口）；配置非空时由
        #     sync_followed_leaders(60s) 负责动态发现，这里不再重复高频调用。
        if not follower_ids:
            try:
                discovered = await feed.scraper.fetch_followed_leaders()
                if discovered:
                    follower_ids |= {lid for lid, _nick in discovered}
            except Exception as exc:  # noqa: BLE001 自动发现失败不阻断轮询
                logger.warning("mode2 自动发现已跟单交易员失败: %s", exc)
        mode_a = [lid for lid in leader_ids if lid not in follower_ids]
        mode_f = [lid for lid in leader_ids if lid in follower_ids]
        # ★ 页面池并发：一次并发拉取全部带单员持仓并差分，避免串行 N×往返
        events_map: dict[str, list] = {}
        for tid, evs in (await feed.poll_leaders_many(mode_a)).items():
            events_map[tid] = evs
        for tid, evs in (await feed.poll_followers_many(mode_f)).items():
            events_map[tid] = evs
        total = await _handle_events(db, events_map)
        await db.commit()
    return total


async def _handle_events(db, events_map: dict[str, list]) -> int:
    """把差分事件统一落库 + 交给 CopyEngine 执行（_poll_live_round 与 _reconcile_once 共用）。

    ★ source_mode 按 leader_id 归属判定：∈ signal_follower_leader_ids → "F"（模式2 跟单），
       否则 "A"（模式1 公开）；side 取事件真实方向（模式2 镜像 long/short）。
    """
    from datetime import datetime, timezone

    from api.models.signal import SourceSignal
    from api.services.copyengine.service import CopyEngine

    follower_ids = set(get_settings().signal_follower_leader_ids)
    total = 0
    for ev in [e for evs in events_map.values() for e in evs]:
        if _is_test_symbol(ev.symbol):  # ★ 测试符号兜底过滤
            logger.info("poll_live: drop test symbol %s", ev.symbol)
            continue
        sig = SourceSignal(
            exchange="gate",
            source_trader_id=ev.trader_id,
            symbol=ev.symbol,
            side=ev.side,  # ★ 模式2 真实方向；模式1 默认 long
            leverage=1,
            qty=0.0,
            percent=ev.percent,  # ★ 带单员持仓占比，供 CopyEngine qty 换算
            action=ev.action,
            source_mode="F" if ev.trader_id in follower_ids else "A",
            opened_at=ev.at,
            received_at=datetime.now(timezone.utc),
            dedupe_key=f"feed-{ev.trader_id}-{ev.symbol}-{ev.action}-{int(ev.at.timestamp())}",
        )
        db.add(sig)
        await db.flush()
        await db.refresh(sig)
        await CopyEngine(db).handle_signal(sig)
        total += 1
    return total


# ── ★ 全量对账（兜底漏采/漂移，独立于 1s 快速轮询）──
@celery_app.task(name="signal.reconcile")
def reconcile_signals() -> str:
    """周期全量对账：对活跃跟单机器人跟随的带单员强制重同步基线。

    即使 1s 轮询某轮漏采/接口失败，对账也会拉最新持仓与基线对齐，
    产出修正的 open/close 事件，防止信号漂移。
    """
    import asyncio

    return asyncio.run(_reconcile_once())


async def _reconcile_once() -> str:
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.bot import CopyBot
    from api.models.signal import Strategy, Trader
    from api.services.signalfeed.service import IncrementalFeedService

    factory = get_session_factory()
    total = 0
    # ★ 单 scraper：对账完关闭浏览器会话
    from api.services.scraper.adapters.gate import GateScraper

    scraper = GateScraper()
    feed = IncrementalFeedService(scraper=scraper)
    try:
        async with factory() as db:
            leader_ids = (
                (
                    await db.execute(
                        select(Trader.trader_id)
                        .join(Strategy, Strategy.trader_id == Trader.id)
                        .join(CopyBot, CopyBot.strategy_id == Strategy.id)
                        .where(CopyBot.status == "active")
                    )
                )
                .scalars()
                .all()
            )
            if not leader_ids:
                return "no active bots"
            follower_ids = set(get_settings().signal_follower_leader_ids)
            mode_a = [lid for lid in leader_ids if lid not in follower_ids]
            mode_f = [lid for lid in leader_ids if lid in follower_ids]
            # ★ 页面池并发：一次并发拉取全部持仓并强制对齐基线
            events_map: dict[str, list] = {}
            for tid, evs in (await feed.reconcile_leaders_many(mode_a)).items():
                events_map[tid] = evs
            for tid, evs in (await feed.reconcile_followers_many(mode_f)).items():
                events_map[tid] = evs
            total = await _handle_events(db, events_map)
            await db.commit()
    finally:
        await scraper.close()  # 释放公开爬虫浏览器
        # ★ 释放登录会话浏览器：避免跨 asyncio.run 事件循环复用旧 _page（NoneType 报错）
        try:
            from api.services.signal_session.service import get_signal_session

            await get_signal_session().close()
        except Exception as exc:  # noqa: BLE001 关闭失败不阻断
            logger.warning("signal_session close fail: %s", exc)
        # ★ 释放异步引擎连接池：asyncio.run 每次新建事件循环，跨循环复用连接会 Event loop is closed
        from api.db.session import get_engine

        await get_engine().dispose()
    return f"reconciled {len(leader_ids)} leaders, {total} correction events"


async def _save_profile(store, trader) -> None:
    """★ G05：画像快照按日 upsert（当日已存在则更新为最新值，保证广场数据新鲜）。"""
    from sqlalchemy import select

    from api.models.signal import TraderProfile

    # trader 可能是 ORM Trader(带 .id) 或 RawTrader(仅外部 trader_id)，统一解析为 DB 主键
    trader_id = getattr(trader, "id", None)
    if trader_id is None:
        from api.models.signal import Trader

        t = await store.db.scalar(
            select(Trader).where(Trader.exchange == "gate", Trader.trader_id == trader.trader_id)
        )
        if t is None:
            return
        trader_id = t.id
    await _upsert_profile(
        store,
        trader_id,
        roi_7d=float(getattr(trader, "roi_7d", 0) or 0),
        roi_30d=float(getattr(trader, "roi_30d", 0) or 0),
        roi_90d=float(getattr(trader, "roi_90d", 0) or 0),
        roi_all=float(getattr(trader, "roi_all", 0) or 0),
        win_rate_30d=float(getattr(trader, "win_rate_30d", 0) or 0),
        win_rate_all=float(getattr(trader, "win_rate_all", 0) or 0),
        max_drawdown=float(getattr(trader, "max_drawdown", 0) or 0),
        trading_days=int(getattr(trader, "trading_days", 0) or 0),
    )


async def _save_followed_profile(store, trader, leader: dict) -> None:
    """为「我账户跟单的交易员」写画像快照（get_leader_by_id 完整多周期字段，按日 upsert）。"""
    await _upsert_profile(
        store,
        trader.id,
        roi_7d=float(leader.get("roi_7d") or 0),
        roi_30d=float(leader.get("roi_30d") or 0),
        roi_90d=float(leader.get("roi_90d") or 0),
        roi_all=float(leader.get("roi_all") or 0),
        win_rate_30d=float(leader.get("win_rate_30d") or 0),
        win_rate_all=float(leader.get("win_rate_all") or 0),
        max_drawdown=float(leader.get("max_drawdown") or 0),
        trading_days=int(leader.get("trading_days") or 0),
    )


async def _upsert_profile(store, trader_id: int, **fields) -> None:
    """★ 画像按日 upsert：当日存在则更新最新值，否则新增。保持广场数据新鲜、无重复行。"""
    from sqlalchemy import select

    from api.models.signal import TraderProfile

    existing = await store.db.scalar(
        select(TraderProfile).where(TraderProfile.trader_id == trader_id, TraderProfile.snapshot_date == date.today())
    )
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        return
    store.db.add(TraderProfile(trader_id=trader_id, snapshot_date=date.today(), **fields))


async def sync_followed_leaders(scraper=None) -> dict:
    """★ 完全自动：把「我账户跟单的交易员」同步为策略广场展示项。

    - fetch_followed_leaders() 获取已跟单交易员 [(leader_id, nick)]（含空仓）
    - 逐个 upsert Trader → 拉画像 → 确保 listed Strategy（跳过 G04）
    - 不再跟单的 listed 策略 → 自动下架（delisted），从策略广场消失
    """
    from api.db.session import get_session_factory
    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalstore.service import SignalStore
    from api.services.strategies.service import StrategyService

    factory = get_session_factory()
    async with factory() as db:
        store = SignalStore(db)
        svc = StrategyService(db)
        scraper = scraper or GateScraper()
        # ★ 复用已登录的持久化会话发现「我账户跟单的交易员」（未登录则退回 scraper 自身 _api）
        from api.services.signal_session.service import get_signal_session

        fetcher = get_signal_session().fetch_api
        followed = await scraper.fetch_followed_leaders(fetcher=fetcher)
        if not followed:
            return {"synced": 0, "listed": 0, "delisted": 0, "reason": "no followed leaders or not logged in"}
        followed_trader_ids: set[int] = set()
        synced = 0
        for lid, nick in followed:
            trader = await store.upsert_trader("gate", str(lid), name=nick)
            try:
                leader = await scraper.get_leader_by_id(str(lid), fetcher=fetcher)
                if leader:
                    await _save_followed_profile(store, trader, leader)
            except Exception as exc:  # noqa: BLE001 画像失败不阻断同步
                logger.warning("sync_followed_leaders 画像同步失败 %s: %s", lid, exc)
            await svc.ensure_followed_strategy(trader.id, nick or str(lid))
            followed_trader_ids.add(trader.id)
            synced += 1
        delisted = await svc.delist_unfollowed(followed_trader_ids)
        await db.commit()
        return {"synced": synced, "listed": len(followed_trader_ids), "delisted": delisted}


# ── ★ 需求补充：定时刷新所有已上架(listed)策略画像，保证策略广场数据新鲜 ──
async def _refresh_listed_profiles() -> dict[str, int]:
    """遍历 status='listed' 的策略，逐一带单员拉最新详情并 upsert 当日画像。

    与每日快照(profile.sync_daily，top50)互补：这里按「实际已上架」精确刷新，
    即便带单员不在排行榜前列也能保持广场数据新鲜。仅刷新画像，不触碰持仓监控。
    """
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.signal import Strategy, Trader
    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalstore.service import SignalStore

    factory = get_session_factory()
    stats = {"updated": 0, "missing": 0, "failed": 0}
    scraper = GateScraper()
    try:
        async with factory() as db:
            store = SignalStore(db)
            rows = (
                (await db.execute(
                    select(Trader, Strategy)
                    .join(Strategy, Strategy.trader_id == Trader.id)
                    .where(Strategy.status == "listed")
                ))
                .all()
            )
            seen: set[int] = set()
            for trader, _strat in rows:
                if trader.id in seen:
                    continue
                seen.add(trader.id)
                try:
                    leader = await scraper.get_leader_by_id(trader.trader_id)
                    if leader is None:
                        stats["missing"] += 1
                        continue
                    await store.upsert_trader("gate", trader.trader_id, name=leader.get("nick") or trader.name,
                                              followers=int(leader.get("followers") or 0))
                    await _save_profile(store, trader)
                    stats["updated"] += 1
                except Exception as exc:  # noqa: BLE001 单个失败不阻断
                    stats["failed"] += 1
                    logger.warning("refresh listed profile %s 失败: %s", trader.trader_id, exc)
            await db.commit()
    finally:
        await scraper.close()
        try:
            from api.services.signal_session.service import get_signal_session

            await get_signal_session().close()
        except Exception as exc:  # noqa: BLE001 关闭失败不阻断
            logger.warning("signal_session close fail: %s", exc)
        from api.db.session import get_engine

        await get_engine().dispose()
    return stats


@celery_app.task(name="signal.refresh_listed_profiles")
def refresh_listed_profiles() -> str:
    """信号源详情定时刷新：所有已上架策略画像按日 upsert，保持策略广场新鲜。"""
    import asyncio

    try:
        return f"listed profiles refreshed: {asyncio.run(_refresh_listed_profiles())}"
    except Exception as exc:  # noqa: BLE001 任务失败不导致 beat 崩溃
        logger.exception("refresh_listed_profiles failed: %s", exc)
        raise
