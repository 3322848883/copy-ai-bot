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
    ★ 2026-08-20 改造：
    - 独立 bulk 浏览器 profile（scraper_bulk_data_dir），不再与 poll_live 抢
      data/scraper 的 ProcessSingleton 锁——此前一次锁冲突整轮 30 分钟采集报废
    - 持仓占比行（opened_at=None，状态非事件）不再入库为 open 信号：此前每轮以
      now() 生成新 dedupe_key，同一持仓每 30 分钟重复记一次 open 污染详情页
    - 上架策略顺带同步持仓基线（与 refresh_listed_profiles 同一兜底通道），
      交易记录行（有真实 data_time 时间戳）仍正常入库
    """
    from sqlalchemy import select

    from api.db.session import get_session_factory, get_engine
    from api.models.signal import Strategy, Trader
    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalstore.service import SignalStore

    settings = get_settings()
    if limit is None:
        limit = settings.signal_scrape_limit
    stats: dict[str, int] = {"traders": 0, "signals": 0, "pos_events": 0, "failed": 0}
    factory = get_session_factory()
    scraper = GateScraper(data_dir=settings.scraper_bulk_data_dir)
    try:
        if not scraper.mock and not await scraper.ensure_browser_ready(90):
            return {**stats, "browser_timeout": 1}
        async with factory() as db:
            store = SignalStore(db)
            # 上架策略的外部 trader_id（顺带做详情数据兜底）
            listed_ext = set(
                (await db.execute(
                    select(Trader.trader_id).join(Strategy, Strategy.trader_id == Trader.id)
                )).scalars().all()
            )
            async for trader, positions in scraper.scrape_all_traders(limit=limit):
                await store.upsert_trader("gate", trader.trader_id, trader.name, trader.followers,
                                          hide_position=trader.hide_position)
                # ★ 交易事件行（有真实 data_time）纯展示入库（不走 ingest 执行管道：
                #   延迟红线会把历史行全部误标 dropped——scrape_all 30 分钟一轮的
                #   trading_view 行从设计上就不具执行资格，入库仅为详情页/信号重放）
                tradable = [p for p in positions if p.opened_at is not None]
                stats["signals"] += await _ingest_trading_records(db, trader.trader_id, tradable)
                # 画像快照（T2.7 ★G05）
                await _save_profile(store, trader)
                stats["traders"] += 1
                # 上架策略：写 A 基线 + 差分产展示信号（无监控策略），与 refresh 同通道。
                # ★ 写前即时复查监控状态（采集循环可能跑数分钟，启动时快照会过期）
                if trader.trader_id in listed_ext:
                    leader_ids, follower_ids = await _load_leader_modes(db)
                    if trader.trader_id in leader_ids and trader.trader_id not in follower_ids:
                        await db.commit()
                        continue  # 模式A被 poll 监控：基线归 poll 管，双写会造假差分
                    emit = trader.trader_id not in follower_ids
                    n = await _sync_positions_display(db, scraper, trader.trader_id, emit_signals=emit)
                    if n < 0:
                        stats["failed"] += 1
                    else:
                        stats["pos_events"] += n
                # ★ 逐交易员提交：单交易员失败 rollback 不连坐（画像/基线/交易记录
                #   攒在同一事务，逐个提交互不影响）
                await db.commit()
    finally:
        await scraper.close()
        await get_engine().dispose()
    return stats


def _to_normalized_signal(trader_id: str, pos):
    """持仓事件行（有真实开仓时间）→ 标准化信号；无效返回 None。"""
    from api.services.normalizer.service import SignalNormalizer

    result = SignalNormalizer().normalize(
        {
            "exchange": "gate",
            "source_trader_id": trader_id,
            "symbol": pos.symbol,
            "side": pos.side,
            "leverage": pos.leverage,
            "qty": pos.qty,
            "action": "open",
            "source_mode": "A",
            "opened_at": pos.opened_at,
        }
    )
    if result.dropped:
        return None
    return result.signal


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
            # ★ 详情页实时持仓缓存（2026-08-20）：有跟单的策略 poll 每轮（~50s）刷新
            #   trader/position（真实方向/均价/标记价/未实现盈亏），无跟单策略由
            #   refresh 每 30 分钟兜底。失败静默——详情页回退占比基线。
            try:
                await _write_live_positions(feed.scraper, leader_ids)
            except Exception as exc:  # noqa: BLE001 缓存失败不影响差分主流程
                logger.warning("live_pos cache refresh fail: %s", exc)
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
    # ★ 单 scraper（bulk profile）：对账完关闭浏览器会话——与 poll 热循环浏览器隔离，
    #   持差分锁期间 poll 跳过轮询但浏览器不被抢占，锁释放后 poll 立即恢复
    from api.services.scraper.adapters.gate import GateScraper

    scraper = GateScraper(data_dir=get_settings().scraper_bulk_data_dir)
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
                # ★ bulk 浏览器就绪重试：scrape_all/refresh 共用 bulk profile，撞车时
                #   ProcessSingleton 锁冲突——90s 内 2s 退避等对方跑完（原实现单次
                #   启动失败整个对账周期报废）
                if not scraper.mock and not await scraper.ensure_browser_ready(90):
                    return "skipped: bulk browser busy"
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
                    # 顺带同步仓位公开状态（admin 模式判断参考；模式B 本身不依赖公开仓位）
                    await store.upsert_trader("gate", str(lid),
                                              followers=int(leader.get("followers") or 0),
                                              hide_position=leader.get("hide_position"))
            except Exception as exc:  # noqa: BLE001 画像失败不阻断同步
                logger.warning("sync_followed_leaders 画像同步失败 %s: %s", lid, exc)
            await svc.ensure_followed_strategy(trader.id, nick or str(lid))
            followed_trader_ids.add(trader.id)
            synced += 1
        delisted = await svc.delist_unfollowed(followed_trader_ids)
        await db.commit()
        return {"synced": synced, "listed": len(followed_trader_ids), "delisted": delisted}


async def _sync_positions_display(db, scraper, trader_id: str, emit_signals: bool) -> int:
    """上架策略详情兜底：拉当前持仓 → 写 A 基线（+ 可选差分产展示信号）。

    - 基线与 poll 同格式 {ts, pos:{symbol: 占比[0,1]}}，详情页 _read_baseline 直接展示
    - emit_signals=True（无任何机器人监控的策略）：与上次基线差分产出 open/close
      信号落库，供详情页「最近交易记录」与信号重放兜底使用；不发 pubsub、不调
      CopyEngine（该策略无活跃机器人，纯展示数据，杜绝误执行）
    - 接口失败返回 -1 计 failed；持仓无变化不产信号（无重复噪音）
    """
    import json as _json
    import time as _time
    from datetime import datetime, timezone

    import redis.asyncio as aioredis

    from api.core.config import get_settings
    from api.models.signal import SourceSignal

    snap = await scraper.fetch_live_positions(trader_id)
    if snap is None:  # 接口失败/风控 → 本轮跳过，不更新基线防抖动
        return -1

    key = f"gate:feed:state:A:{trader_id}"
    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        raw = await r.get(key)
        old: dict[str, float] = {}
        old_sides: dict[str, str] = {}
        if raw:
            try:
                d = _json.loads(raw)
                pos = d.get("pos")
                if isinstance(pos, dict):
                    old = {k: float(v) for k, v in pos.items()}
                sides = d.get("sides")
                if isinstance(sides, dict):
                    old_sides = {k: str(v) for k, v in sides.items()}
            except (ValueError, TypeError):  # noqa: BLE001 损坏基线按无基线处理
                old = {}
        opened = sorted(set(snap) - set(old))
        live_sides: dict[str, str] = {}
        if emit_signals and old != snap:
            now = datetime.now(timezone.utc)
            ts = int(now.timestamp())
            # ★ open 方向真实化（2026-08-23）：实时拉 trader/position 取真实
            #   long/short（公开带单员）；隐藏/失败 → {} 回退 long
            if opened:
                try:
                    rows = await scraper.fetch_leader_positions_live(trader_id)
                    live_sides = {
                        row["symbol"]: row["side"]
                        for row in rows or []
                        if row.get("symbol") and row.get("side") in ("long", "short")
                    }
                except Exception:  # noqa: BLE001 方向拉取失败不阻断信号产出
                    live_sides = {}
            for sym in opened:  # 新开仓
                db.add(SourceSignal(
                    exchange="gate", source_trader_id=trader_id, symbol=sym,
                    side=live_sides.get(sym, "long"),
                    leverage=1, qty=0.0, percent=snap[sym] or None, action="open",
                    source_mode="A", opened_at=now, received_at=now,
                    dedupe_key=f"refresh-{trader_id}-{sym}-open-{ts}",
                ))
            for sym in sorted(set(old) - set(snap)):  # 已平仓：回查基线原方向
                db.add(SourceSignal(
                    exchange="gate", source_trader_id=trader_id, symbol=sym,
                    side=old_sides.get(sym, "long"),
                    leverage=1, qty=0.0, percent=None, action="close",
                    source_mode="A", opened_at=now, received_at=now,
                    dedupe_key=f"refresh-{trader_id}-{sym}-close-{ts}",
                ))
        # 基线带 sides 快照：live_sides 覆盖全量方向，未拉取时沿用旧 sides
        if opened and live_sides:
            new_sides = {sym: live_sides.get(sym, "long") for sym in snap}
        else:
            new_sides = {sym: old_sides.get(sym, "long") for sym in snap}
        await r.set(key, _json.dumps({"ts": _time.time(), "pos": snap, "sides": new_sides}))
        return len(set(snap) ^ set(old)) if emit_signals else 0
    finally:
        await r.aclose()


async def _ingest_trading_records(db, trader_id: str, records: list) -> int:
    """交易记录行入库（trading_view 历史行，纯展示）：预查 dedupe 过滤旧记录。

    ★ 必须直接 db.add（dropped=False），不走 store.ingest：
      - ingest 的延迟红线（mode A >10s）会拦截全部历史交易行——红线是为
        「老信号不得触发跟单执行」设计的执行风控，trading_view 行本来就是
        几分钟~几天前的历史记录，作为展示数据不该被执行管道过滤（曾把
        refresh 补拉的 1692 条全部误标 dropped）
      - ingest 对有效信号发布 signal.new pubsub → consumer 派发跟单任务，
        展示数据绝不能进执行管道（防无谓执行与 pubsub 洪水）
    ★ pre-check 必需：批内/跨批重复 dedupe_key 若触发 IntegrityError，
      rollback 会把同事务攒着的画像/差分信号一并回滚。
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from api.models.signal import SourceSignal

    fresh = []
    keys: list[str] = []
    for pos in records:
        if pos.opened_at is None:
            continue
        ns = _to_normalized_signal(trader_id, pos)
        if ns is None:
            continue
        fresh.append(ns)
        keys.append(ns.dedupe_key())
    if not fresh:
        return 0
    existing = set(
        (await db.execute(
            select(SourceSignal.dedupe_key).where(SourceSignal.dedupe_key.in_(keys))
        )).scalars().all()
    )
    now = datetime.now(timezone.utc)
    n = 0
    for ns in fresh:
        dk = ns.dedupe_key()
        if dk in existing:
            continue
        existing.add(dk)  # 批内去重（同 symbol 同秒多行）
        db.add(SourceSignal(
            exchange=ns.exchange,
            source_trader_id=ns.source_trader_id,
            symbol=ns.symbol,
            side=ns.side,
            leverage=ns.leverage,
            qty=ns.qty,
            action=ns.action,
            source_mode=ns.source_mode,
            opened_at=ns.opened_at,
            received_at=now,
            dedupe_key=dk,
            dropped=False,
        ))
        n += 1
    return n


async def _upsert_closed_positions(db, trader_pk: int, rows: list[dict]) -> int:
    """已平仓记录入库（close_position 接口，纯展示）：gate_order_id 去重，返回新插入行数。

    只 db.add 不 commit（refresh 循环逐交易员统一提交）；
    pre-check 必需：unique 冲突的 rollback 会连坐同事务的画像/基线写入。
    """
    from sqlalchemy import select

    from api.models.signal import ClosedPosition

    ids = [r["gate_order_id"] for r in rows if r.get("gate_order_id")]
    if not ids:
        return 0
    existing = set(
        (await db.execute(
            select(ClosedPosition.gate_order_id).where(
                ClosedPosition.trader_id == trader_pk,
                ClosedPosition.gate_order_id.in_(ids),
            )
        )).scalars().all()
    )
    n = 0
    for r in rows:
        gid = r.get("gate_order_id")
        if not gid or gid in existing:
            continue
        db.add(ClosedPosition(trader_id=trader_pk, **r))
        n += 1
    return n


# ── ★ 详情页实时持仓缓存（2026-08-20）：trader/position 接口含真实方向/均价/
#    标记价/未实现盈亏，详情页 positions 优先读它（替代占比基线的 null 字段+方向缺失）。
#    写入方：poll_live 每轮（有跟单策略 ~50s 实时）/ refresh 每 30 分钟（无跟单兜底）。──
LIVE_POS_KEY = "gate:leader:live_pos:{tid}"
LIVE_POS_TTL = 40 * 60  # 覆盖 refresh 30min 周期 + 容错


async def _write_live_positions(scraper, trader_ids: list[str]) -> int:
    """批量拉实时持仓写 Redis（详情页直读，不落库）。失败静默（详情页回退基线）。

    ★ 按交易员节流 10s（2026-08-20）：详情页展示 10s 新鲜度足够；原实现每轮差分
      后串行拉全部交易员（每个 ~1.4s），把差分轮询从 ~1s 拖到 ~5s——信号延迟红线
      A=10s，展示缓存不该吃掉轮询预算。节流后差分轮回到 ~2s/轮。
    """
    if not trader_ids or scraper.mock:
        return 0
    import json
    import time as _time

    import redis.asyncio as aioredis

    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    written = 0
    try:
        for tid in trader_ids:
            try:
                last = await r.get(f"gate:leader:live_pos:ts:{tid}")
                if last and (_time.time() - float(last)) < 10:
                    continue
                positions = await scraper.fetch_leader_positions_live(tid)
            except Exception:  # noqa: BLE001 单个失败不阻断
                continue
            pipe = r.pipeline()
            pipe.set(
                LIVE_POS_KEY.format(tid=tid),
                json.dumps({"ts": _time.time(), "positions": positions}),
                ex=LIVE_POS_TTL,
            )
            pipe.set(f"gate:leader:live_pos:ts:{tid}", str(_time.time()), ex=120)
            await pipe.execute()
            written += 1
    finally:
        await r.aclose()
    return written


async def _backfill_profit_chart(db, trader_db_id: int, gate_trader_id: str, scraper) -> int:
    """profit_chart 每日累计收益序列回填 trader_profiles（收益曲线历史）。

    ★ 解决"7d/30d 曲线无历史"：系统上线仅数天，按日快照最多 2-3 行，区间曲线无意义。
      profit_chart（网页收益走势图同源）提供近 30 天每日累计收益率——按日期 upsert，
      曲线立即成型且与 Gate 网页一致（simple_profit_rate 口径）。
    已存在日期行：仅更新 roi_all（profit_chart 口径更权威，修正上线首日 profit_rate
    含分成口径混入的脏值）；新日期行：插入（roi_all 之外字段为 0，卡片只读最新行）。
    """
    from datetime import date as _date

    from sqlalchemy import select

    from api.models.signal import TraderProfile

    try:
        chart = await scraper.fetch_profit_chart(gate_trader_id)
    except Exception:  # noqa: BLE001 拉取失败不阻断 refresh 主流程
        return 0
    if not chart:
        return 0
    dates = [row["date"] for row in chart]
    existing = {
        p.snapshot_date: p
        for p in (await db.execute(
            select(TraderProfile).where(
                TraderProfile.trader_id == trader_db_id,
                TraderProfile.snapshot_date.in_(dates),
            )
        )).scalars().all()
    }
    n = 0
    for row in chart:
        d: _date = row["date"]
        p = existing.get(d)
        if p is not None:
            p.roi_all = row["roi_all"]
        else:
            db.add(TraderProfile(trader_id=trader_db_id, snapshot_date=d, roi_all=row["roi_all"]))
        n += 1
    return n


# ── ★ 需求补充：定时刷新所有已上架(listed)策略画像，保证策略广场数据新鲜 ──
async def _refresh_listed_profiles() -> dict[str, int]:
    """遍历 status='listed' 的策略，逐一带单员拉最新详情并 upsert 当日画像。

    与每日快照(profile.sync_daily，top50)互补：这里按「实际已上架」精确刷新，
    即便带单员不在排行榜前列也能保持广场数据新鲜。

    ★ 详情数据兜底（2026-08-20）：无活跃机器人的上架策略不被 poll_live 监控 →
    永无信号 → 详情页持仓/交易记录恒空。此处顺带拉当前持仓 + 交易记录：
    - 写 A 基线（gate:feed:state:A:{tid}，与 poll 同格式）→ 详情页 positions
      走基线展示真实持仓+占比（替代信号重放的 null 字段/幽灵持仓）
    - 无监控策略与上次基线差分产出 open/close 展示信号（纯落库，不发 pubsub、
      不触发 CopyEngine——无机器人不存在执行路径）
    - 补拉 trading_view 交易记录行（真实 data_time，dedupe 跨轮去重）→
      详情页「最近交易记录」持续积累（scrape_all 只覆盖排行榜 top8，这里是
      大部分上架策略唯一的交易记录来源）
    ★ 模式A被 poll 监控的策略跳过持仓写入：poll 以 A 基线做差分驱动真实下单，
      此处双写基线会制造假差分 → 误发真实订单。
    ★ 不再持差分锁（2026-08-20）：bulk profile 浏览器与 poll 并行互不干扰，
      此前持锁 300s 会让 poll 整段致盲。改为写基线前逐交易员复查监控状态，
      任务中途新激活的机器人对应交易员跳过基线写入（防 stale 覆盖 → 假差分）。
    """
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.signal import Strategy, Trader
    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalstore.service import SignalStore

    factory = get_session_factory()
    stats = {"updated": 0, "missing": 0, "failed": 0, "pos_events": 0, "trade_rows": 0, "chart_rows": 0, "closed_rows": 0}
    scraper = GateScraper(data_dir=get_settings().scraper_bulk_data_dir)
    try:
        if not scraper.mock and not await scraper.ensure_browser_ready(90):
            return {**stats, "browser_timeout": 1}
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
                                              followers=int(leader.get("followers") or 0),
                                              hide_position=leader.get("hide_position"))
                    # ★ 写「拉到的 leader dict」（_save_profile 读 ORM trader 属性恒为 0，
                    #   曾把全部已上架画像周期性清零）
                    await _save_followed_profile(store, trader, leader)
                    stats["updated"] += 1
                    # ★ 逐交易员复查监控状态（任务可能跑数分钟，启动时的快照会过期）：
                    #   中途被机器人激活/转模式B的交易员，其基线归属已变，跳过写入
                    leader_ids, follower_ids = await _load_leader_modes(db)
                    if trader.trader_id in leader_ids and trader.trader_id not in follower_ids:
                        await db.commit()
                        continue  # 模式A被 poll 监控：基线归 poll 管，双写会造假差分
                    # 模式B被监控（poll 只写 B 基线）：仅写 A 基线改善详情展示，不产信号
                    # （镜像信号已由 poll 实时产出，混入公开持仓事件会污染信号流）
                    emit = trader.trader_id not in follower_ids
                    n = await _sync_positions_display(db, scraper, trader.trader_id, emit_signals=emit)
                    if n < 0:
                        stats["failed"] += 1
                    else:
                        stats["pos_events"] += n
                    # ★ 交易记录兜底（2026-08-20）：无监控策略的详情页「最近交易记录」
                    #   原本只有持仓差分事件（持仓没变就零新记录 → 大部分策略恒 2-4 条）。
                    #   补拉 trading_view 近期交易行（真实 data_time → dedupe 跨轮去重，
                    #   重复轮次零噪音），交易记录随时间自然积累到几十条。
                    #   scrape_all 只覆盖排行榜 top8，大部分上架策略不在榜单——这里是
                    #   它们唯一的交易记录来源。
                    if emit:
                        records = await scraper.fetch_trading_records(trader.trader_id)
                        stats["trade_rows"] += await _ingest_trading_records(
                            db, trader.trader_id, records
                        )
                    # ★ 详情页实时持仓缓存（2026-08-20）：无跟单策略的 30 分钟兜底
                    #   （有跟单的由 poll 每轮覆盖，此处重复写幂等无害）
                    try:
                        await _write_live_positions(scraper, [trader.trader_id])
                    except Exception as exc:  # noqa: BLE001 缓存失败不阻断
                        logger.warning("live_pos cache %s fail: %s", trader.trader_id, exc)
                    # ★ 已平仓记录采集（2026-08-22）：close_position 接口含真实方向/
                    #   已实现盈亏/开平仓均价，是详情页交易记录的数据源；对隐藏持仓
                    #   交易员同样返回（历史平仓不受 is_hide 屏蔽）。纯展示数据与
                    #   监控模式无关，无条件采集（gate_order_id 跨轮去重）。
                    try:
                        closed = await scraper.fetch_closed_positions(trader.trader_id)
                        if closed:
                            stats["closed_rows"] += await _upsert_closed_positions(db, trader.id, closed)
                    except Exception as exc:  # noqa: BLE001 单项失败不阻断
                        logger.warning("closed_positions %s fail: %s", trader.trader_id, exc)
                    # ★ 收益曲线历史回填（2026-08-20）：profit_chart 近 30 天每日累计
                    #   收益率 upsert 进 trader_profiles——上线首日快照只有 1-2 行，
                    #   7d/30d 区间曲线无意义；回填后与 Gate 网页走势图一致。
                    try:
                        stats["chart_rows"] += await _backfill_profit_chart(
                            db, trader.id, trader.trader_id, scraper
                        )
                    except Exception as exc:  # noqa: BLE001 回填失败不阻断
                        logger.warning("profit_chart %s fail: %s", trader.trader_id, exc)
                    # ★ 逐交易员提交（原最后统一提交）：ingest 撞重复 key 的 rollback
                    #   会把事务里攒着的画像/差分信号一并回滚，逐个提交互不影响
                    await db.commit()
                except Exception as exc:  # noqa: BLE001 单个失败不阻断
                    await db.rollback()
                    stats["failed"] += 1
                    logger.warning("refresh listed profile %s 失败: %s", trader.trader_id, exc)
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


@celery_app.task(name="signal.vacuum_retention")
def vacuum_retention() -> str:
    """数据保留期清理：删除超期的源信号、已关闭的老持仓快照。

    - source_signals：超过 signal_retention_days 的记录全部删除
    - position_snapshots：超过 position_snapshot_retention_days 且 is_open=False 的记录删除
    每日凌晨执行，避免表无限增长拖慢查询。
    """
    import asyncio

    try:
        return asyncio.run(_vacuum_retention_async())
    except Exception as exc:  # noqa: BLE001
        logger.exception("vacuum_retention failed: %s", exc)
        raise


async def _vacuum_retention_async() -> str:
    """async 核心：按保留期批量清理过期数据。"""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    from api.db.session import get_session_factory
    from api.models.bot import PositionSnapshot
    from api.models.signal import SourceSignal

    settings = get_settings()
    now = datetime.now(timezone.utc)
    signal_cutoff = now - timedelta(days=settings.signal_retention_days)
    snapshot_cutoff = now - timedelta(days=settings.position_snapshot_retention_days)

    factory = get_session_factory()
    async with factory() as db:
        # 1. 清理超期源信号
        r_sig = await db.execute(
            delete(SourceSignal).where(SourceSignal.received_at < signal_cutoff)
        )
        # 2. 清理超期且已关闭的持仓快照
        r_snap = await db.execute(
            delete(PositionSnapshot).where(
                PositionSnapshot.is_open.is_(False),
                PositionSnapshot.created_at < snapshot_cutoff,
            )
        )
        await db.commit()
        return (
            f"vacuum: deleted {r_sig.rowcount} signals (>{settings.signal_retention_days}d), "
            f"{r_snap.rowcount} closed snapshots (>{settings.position_snapshot_retention_days}d)"
        )
