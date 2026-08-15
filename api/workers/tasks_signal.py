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
    try:
        while time.time() < deadline:
            try:
                events_total += await _poll_live_round(feed)
            except Exception as exc:  # noqa: BLE001 单轮失败不中断循环
                logger.error("signal.poll_live 单轮失败: %s", exc)
            rounds += 1
            await asyncio.sleep(interval)
    finally:
        await scraper.close()  # 释放浏览器会话
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
        # ★ 模式2 自动发现：合并运行中已跟单交易员（含空仓），确保不漏跟单
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
        await scraper.close()  # 释放浏览器会话
        # ★ 释放异步引擎连接池：asyncio.run 每次新建事件循环，跨循环复用连接会 Event loop is closed
        from api.db.session import get_engine

        await get_engine().dispose()
    return f"reconciled {len(leader_ids)} leaders, {total} correction events"


async def _save_profile(store, trader) -> None:
    """★ G05：按日快照（roi_7d/30d/90d/all + win_rate_all + trading_days）。"""
    from sqlalchemy import select

    from api.models.signal import Trader, TraderProfile

    t = await store.db.scalar(select(Trader).where(Trader.exchange == "gate", Trader.trader_id == trader.trader_id))
    if t is None:
        return
    existing = await store.db.scalar(
        select(TraderProfile).where(TraderProfile.trader_id == t.id, TraderProfile.snapshot_date == date.today())
    )
    if existing:
        return  # 今日已快照
    store.db.add(
        TraderProfile(
            trader_id=t.id,
            snapshot_date=date.today(),
            roi_7d=trader.roi_7d,
            roi_30d=trader.roi_30d,
            roi_90d=trader.roi_90d,
            roi_all=trader.roi_all,
            win_rate_30d=trader.win_rate_30d,
            win_rate_all=trader.win_rate_all,
            max_drawdown=trader.max_drawdown,
            trading_days=trader.trading_days,
        )
    )
