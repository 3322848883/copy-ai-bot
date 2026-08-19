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


async def run_scrape_all(limit: int | None = None) -> dict[str, int]:
    """采集核心（async）：排行榜 → 持仓 → 标准化 → 入库 → 画像快照。

    dev 环境用 mock 数据跑通全链路；生产接入 Playwright 适配器。
    """
    from api.db.session import get_session_factory
    from api.services.normalizer.service import SignalNormalizer
    from api.services.scraper.service import ScraperService
    from api.services.signalstore.service import SignalStore

    if limit is None:
        limit = get_settings().signal_scrape_limit
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
    """触发公开带单广场采集（模式 A，当前已接入 Gate，其他交易所规划中）。"""
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
    # ★ 完全自动：把「我账户跟单的交易员」同步为策略广场展示项。
    #   ★ 降频 60s→默认600s（可配 signal_follow_sync_interval）：同步需拉起登录会话浏览器，
    #     与 admin 远程操作/搜索争抢 user_data_dir（ProcessSingleton 锁）；跟单关系变化
    #     本身是低频事件，高频同步只会放大争抢窗口。
    #   ★ 上次同步时间存 Redis（跨任务持久）：poll_live 每 60s 被 beat 重踢一次，
    #     任务内变量每次归零会让每轮任务开头都同步——worker 浏览器常驻、admin 永远拉不起。
    SYNC_INTERVAL = float(get_settings().signal_follow_sync_interval)
    _SYNC_TS_KEY = "signal:follow_sync:last_ts"
    try:
        while time.time() < deadline:
            try:
                events_total += await _poll_live_round(feed)
            except Exception as exc:  # noqa: BLE001 单轮失败不中断循环
                logger.error("signal.poll_live 单轮失败: %s", exc)
            rounds += 1
            last_sync = _redis_get_float(_SYNC_TS_KEY)
            if last_sync is None or (time.time() - last_sync) >= SYNC_INTERVAL:
                try:
                    await sync_followed_leaders(scraper=scraper)
                    _redis_set_float(_SYNC_TS_KEY, time.time())
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


# ── ★ 差分互斥锁：poll_live（1s 轮询）与 reconcile（10min 对账）是独立 Celery 进程，
#    共同读写同一 Redis 基线 gate:feed:state:{trader_id}——并发差分会把同一开/平仓
#    事件各产出一次，导致重复真实下单（双倍买入/平仓）。二者必须互斥。──
_DIFF_LOCK_KEY = "signal:diff:lock"


def _redis_get_float(key: str) -> float | None:
    """读 Redis float（跨任务持久状态）。Redis 故障返回 None（视为未记录）。"""
    try:
        import redis as _redis

        r = _redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        v = r.get(key)
        r.close()
        return float(v) if v else None
    except Exception:  # noqa: BLE001
        return None


def _redis_set_float(key: str, value: float) -> None:
    try:
        import redis as _redis

        r = _redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        r.set(key, value)
        r.close()
    except Exception:  # noqa: BLE001
        pass


def _acquire_diff_lock(holder: str, ttl_s: int) -> tuple[bool, str]:
    """返回 (是否获得锁, 持有令牌)。Redis 故障时放行（退回无锁旧行为）。"""
    import uuid

    from redis import Redis

    token = f"{holder}:{uuid.uuid4().hex[:8]}"
    try:
        r = Redis.from_url(get_settings().redis_url, decode_responses=True)
        got = bool(r.set(_DIFF_LOCK_KEY, token, nx=True, ex=ttl_s))
        r.close()
    except Exception as exc:  # noqa: BLE001 Redis 故障不阻断差分（退回旧行为）
        logger.warning("diff lock acquire failed: %s", exc)
        return True, ""
    return got, token if got else ""


def _release_diff_lock(token: str) -> None:
    if not token:
        return
    try:
        from redis import Redis

        r = Redis.from_url(get_settings().redis_url, decode_responses=True)
        # 仅释放自己持有的锁（值匹配），防止误删他人的锁
        if r.get(_DIFF_LOCK_KEY) == token:
            r.delete(_DIFF_LOCK_KEY)
        r.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("diff lock release failed: %s", exc)


async def _poll_live_round(feed) -> int:
    """单轮轮询：查活跃机器人 → 按模式对每个带单员做持仓差分 → 产出信号。

    ★ 模式路由（_load_leader_modes）：Strategy.source='B'（跟单同步上架）→ 模式2 镜像差分；
       'A'（公开广场）→ 模式1 公开差分。判定基于持久数据，会话抖动不再引起模式跳变。
    ★ 模式2 自动发现由 sync_followed_leaders（600s）负责：新跟单 → source='B' → 下轮自动转模式2。
    """
    from api.db.session import get_session_factory

    factory = get_session_factory()
    total = 0
    async with factory() as db:
        leader_ids, follower_ids = await _load_leader_modes(db)
        if not leader_ids:
            return 0
        mode_a = [lid for lid in leader_ids if lid not in follower_ids]
        mode_f = [lid for lid in leader_ids if lid in follower_ids]
        # ★ 差分互斥：reconcile 正在强制对齐基线时本轮跳过（由对账兜底），避免同一事件双发
        got, token = _acquire_diff_lock("poll", ttl_s=30)
        if not got:
            logger.info("poll round skipped: reconcile holding diff lock")
            return 0
        try:
            # ★ 页面池并发：一次并发拉取全部带单员持仓并差分，避免串行 N×往返
            events_map: dict[str, list] = {}
            for tid, evs in (await feed.poll_leaders_many(mode_a)).items():
                events_map[tid] = evs
            for tid, evs in (await feed.poll_followers_many(mode_f)).items():
                events_map[tid] = evs
            total = await _handle_events(db, events_map, follower_ids)
            await db.commit()
        finally:
            _release_diff_lock(token)
    return total


async def _load_leader_modes(db) -> tuple[list[str], set[str]]:
    """加载活跃机器人监控的带单员及其差分模式（poll 与 reconcile 共用）。

    ★ 模式判定以 Strategy.source 为准（持久数据，sync_followed_leaders 维护）：
      source='B' → 模式2 镜像差分；'A'（或未标记）→ 模式1 公开差分。
      ★ 不再用 fetch_followed_leaders 瞬时结果决定模式——登录会话抖动会让同一带单员
      在 A/B 间跳变，A/B 基线互相污染产出乒乓假信号（开4平2→开2平4 循环）。
      自动发现仍由 sync_followed_leaders（600s）负责：发现新跟单 → ensure_followed_strategy
      写 source='B' → 下一轮差分自动转模式2，判定永不抖动。
    """
    from sqlalchemy import select

    from api.models.bot import CopyBot
    from api.models.signal import Strategy, Trader

    rows = (
        await db.execute(
            select(Trader.trader_id, Strategy.source)
            .join(Strategy, Strategy.trader_id == Trader.id)
            .join(CopyBot, CopyBot.strategy_id == Strategy.id)
            .where(CopyBot.status == "active")
        )
    ).all()
    configured = set(get_settings().signal_follower_leader_ids)
    leaders: dict[str, str] = {}
    for tid, src in rows:
        mode = "B" if (src == "B" or tid in configured) else "A"
        # 同一交易员多策略：任一 B 即 B（宁镜像勿公开，防基线污染）
        if leaders.get(tid) != "B":
            leaders[tid] = mode
    follower_ids = {tid for tid, m in leaders.items() if m == "B"}
    return list(leaders), follower_ids


async def _handle_events(db, events_map: dict[str, list], follower_ids: set[str] | None = None) -> int:
    """把差分事件统一落库 + 交给 CopyEngine 执行（_poll_live_round 与 _reconcile_once 共用）。

    ★ source_mode 按 leader_id 归属判定：∈ follower_ids → "B"（模式2 跟单），
       否则 "A"（模式1 公开）；side 取事件真实方向（模式2 镜像 long/short）。
    ★ follower_ids 必须由调用方传入（_load_leader_modes 的持久判定结果）：
       自行读静态配置会与调用方集合不一致，跟单 leader 被错标为模式 A。
    ★ 统一标记 "A"/"B"：风控引擎与 SignalStore 的延迟红线按 "A"/"B" 判定，历史
       "F" 标记会绕过全部延迟红线（风控裸奔）。
    """
    from datetime import datetime, timezone

    from api.models.signal import SourceSignal
    from api.services.copyengine.service import CopyEngine

    if follower_ids is None:
        follower_ids = set(get_settings().signal_follower_leader_ids)
    total = 0
    for ev in [e for evs in events_map.values() for e in evs]:
        if _is_test_symbol(ev.symbol):  # ★ 测试符号兜底过滤
            logger.info("poll_live: drop test symbol %s", ev.symbol)
            continue
        is_mode_b = ev.trader_id in follower_ids
        sig = SourceSignal(
            exchange="gate",
            source_trader_id=ev.trader_id,
            symbol=ev.symbol,
            side=ev.side,  # ★ 模式2 真实方向；模式1 默认 long
            leverage=1,
            qty=0.0,
            # ★ 模式A：带单员持仓占比∈[0,1]，供 CopyEngine qty 换算。
            #   模式B：ev.percent 是跟单镜像张数（如 30 张）非占比——传入会被
            #   _effective_percent clamp 成 1.0（100% 全仓），必须置 None。
            percent=(ev.percent if not is_mode_b else None),
            action=ev.action,
            source_mode="B" if is_mode_b else "A",
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
    from api.db.session import get_session_factory
    from api.services.signalfeed.service import IncrementalFeedService

    factory = get_session_factory()
    total = 0
    # ★ 单 scraper：对账完关闭浏览器会话
    from api.services.scraper.adapters.gate import GateScraper

    scraper = GateScraper()
    feed = IncrementalFeedService(scraper=scraper)
    try:
        async with factory() as db:
            leader_ids, follower_ids = await _load_leader_modes(db)
            if not leader_ids:
                return "no active bots"
            mode_a = [lid for lid in leader_ids if lid not in follower_ids]
            mode_f = [lid for lid in leader_ids if lid in follower_ids]
            # ★ 差分互斥：poll_live 正在差分时跳过本轮（下个周期再来），避免同一事件双发
            got, token = _acquire_diff_lock("reconcile", ttl_s=600)
            if not got:
                return "skipped: poll holding diff lock"
            try:
                # ★ 页面池并发：一次并发拉取全部持仓并强制对齐基线
                events_map: dict[str, list] = {}
                for tid, evs in (await feed.reconcile_leaders_many(mode_a)).items():
                    events_map[tid] = evs
                for tid, evs in (await feed.reconcile_followers_many(mode_f)).items():
                    events_map[tid] = evs
                total = await _handle_events(db, events_map, follower_ids)
                await db.commit()
            finally:
                _release_diff_lock(token)
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
                    # ★ detail 接口的 nick 恒为 "Leader{id}" 占位符（无昵称字段），
                    #   传入会覆盖 fetch_followed_leaders 已写入的真实昵称——不传 name。
                    await store.upsert_trader("gate", trader.trader_id,
                                              followers=int(leader.get("followers") or 0))
                    # ★ 写「拉到的 leader dict」（_save_profile 读 ORM trader 属性恒为 0，
                    #   曾把全部已上架画像周期性清零）
                    await _save_followed_profile(store, trader, leader)
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
