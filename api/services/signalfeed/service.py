# 增量信号差分引擎（★实时信号：只执行新开仓/新平仓，存量持仓仅作基线）
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.services.scraper.adapters.gate import GateScraper

logger = logging.getLogger("signal-saas.signalfeed")

STATE_TTL_S = 7 * 24 * 3600  # 状态保留 7 天
# ★ 模式隔离键：同一交易员可能既有公开广场差分（A）又有跟单镜像差分（B），
#   二者持仓视图完全不同（公开持仓 vs 我账户镜像仓位）——共用键会把彼此基线
#   互相覆盖，产出"开4平2→开2平4"乒乓假信号。mode ∈ {"A","B"}。
STATE_PREFIX = "gate:feed:state:{mode}:{trader_id}"


@dataclass
class FeedEvent:
    """差分产生的一次信号事件（只含变化，不重复存量）。"""

    trader_id: str
    symbol: str
    action: str  # open / close
    percent: float = 0.0
    side: str = "long"  # ★ 模式2 真实方向（long/short）；模式1 默认为 long
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class IncrementalFeedService:
    """Gate 带单员持仓差分：Redis 存上次快照，轮询对比产出开/平仓事件。

    - 首次采集（无基线）→ 只建基线，不产出信号（存量持仓不执行）
    - 新增 symbol → open 事件（执行新开仓）
    - 消失 symbol → close 事件（执行新平仓）
    - 持仓占比变化（symbol 仍存在）→ 不产出（非开平仓事件）

    ★ 阈值过滤：低于 signal_change_threshold 的微仓视为噪音，不触发信号
    ★ 全量对账：超过 signal_reconcile_interval 未同步则强制重同步基线防漂移
    """

    def __init__(self, db: AsyncSession | None = None, redis: Any | None = None, scraper: GateScraper | None = None) -> None:
        settings = get_settings()
        self.db = db
        self._redis = redis
        self._settings = settings
        # ★ 从 config 读取，便于测试注入
        self.threshold = settings.signal_change_threshold
        self.reconcile_interval = settings.signal_reconcile_interval
        self.scraper = scraper or GateScraper()

    async def _redis_client(self) -> Any:
        if self._redis is None:
            self._redis = aioredis.from_url(self._settings.redis_url, decode_responses=True)
        return self._redis

    @staticmethod
    def _state_key(trader_id: str, mode: str) -> str:
        return STATE_PREFIX.format(mode=mode, trader_id=trader_id)

    async def get_state(self, trader_id: str, mode: str = "A") -> dict[str, Any] | None:
        """返回上次状态；None 表示尚无基线（从未轮询）。

        结构：{"ts": float(上次轮询时刻), "pos": {sym: percent}, "sides": {sym: long/short}}。
        sides 为该轮持仓方向快照（2026-08-23）：close 事件回查"消失仓位原方向"，
        执行侧据它正确反向平仓。旧结构无 sides → {}。
        """
        r = await self._redis_client()
        raw = await r.get(self._state_key(trader_id, mode))
        if raw is None:
            return None
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(d, dict):
            return None
        pos = d.get("pos")
        ts = d.get("ts")
        # 兼容旧版纯 dict 快照：无 ts 视为未知
        if not isinstance(pos, dict):
            return None
        sides = d.get("sides")
        if not isinstance(sides, dict):
            sides = {}
        return {"ts": ts, "pos": pos, "sides": sides}

    async def set_state(
        self, trader_id: str, state: dict[str, float], ts: float | None = None,
        mode: str = "A", sides: dict[str, str] | None = None,
    ) -> None:
        r = await self._redis_client()
        await r.set(
            self._state_key(trader_id, mode),
            json.dumps({"ts": ts if ts is not None else time.time(), "pos": state, "sides": sides or {}}),
            ex=STATE_TTL_S,
        )

    async def clear_state(self, trader_id: str, mode: str = "A") -> None:
        r = await self._redis_client()
        await r.delete(self._state_key(trader_id, mode))

    # ── 持仓差分核心（poll 与 reconcile 共用）──
    @staticmethod
    def _diff(
        trader_id: str,
        prev: dict[str, float],
        current: dict[str, float],
        *,
        emit_size_changes: bool = False,
    ) -> list[FeedEvent]:
        """对比快照，产出开平仓；模式 B 额外产出加仓/减仓。

        模式 B 的数值是登录跟单账户里的真实镜像数量，数量变化可可靠代表交易；
        模式 A 是组合占比，会随价格自然波动，禁止据此生成真实 add/reduce。
        """
        events: list[FeedEvent] = []
        cur_keys = set(current)
        prev_keys = set(prev)
        for sym in cur_keys - prev_keys:
            events.append(FeedEvent(trader_id=trader_id, symbol=sym, action="open", percent=current[sym]))
        for sym in prev_keys - cur_keys:
            events.append(FeedEvent(trader_id=trader_id, symbol=sym, action="close"))
        if emit_size_changes:
            for sym in cur_keys & prev_keys:
                old = float(prev[sym])
                new = float(current[sym])
                delta = new - old
                epsilon = max(abs(old), abs(new), 1.0) * 1e-9
                if delta > epsilon:
                    # 相对原仓位的新增比例，供用户机器人按自身仓位同比例加仓。
                    ratio = delta / old if old > 0 else 1.0
                    events.append(FeedEvent(
                        trader_id=trader_id, symbol=sym, action="add",
                        percent=max(0.0, ratio),
                    ))
                elif delta < -epsilon:
                    # 相对原仓位的减仓比例；执行侧按本账户当前仓位同比例减仓。
                    ratio = (old - new) / old if old > 0 else 1.0
                    events.append(FeedEvent(
                        trader_id=trader_id, symbol=sym, action="reduce",
                        percent=max(0.0, min(1.0, ratio)),
                    ))
        return events

    def _filter(self, current: dict[str, float], mode: str = "A") -> dict[str, float]:
        """过滤无效仓位；占比阈值只适用于模式 A。

        模式 A 的值是持仓占比（0.005=0.5%），模式 B 的值是实际币数量
        （例如 ETH 0.001）。旧实现混用同一阈值，会让小额镜像仓位永远不产生信号。
        """
        positive = {sym: value for sym, value in current.items() if value > 0}
        if mode == "A" and self.threshold and self.threshold > 0:
            return {sym: p for sym, p in positive.items() if p >= self.threshold}
        return positive

    async def poll_leader(self, trader_id: str) -> list[FeedEvent]:
        """轮询单个带单员：当前持仓 vs 上次快照 → 开/平仓事件。

        - 接口失败（current=None）→ 跳过本轮，不更新基线（防抖动）
        - 首次（无基线）→ 建基线，不产出（存量持仓不执行）
        - 真空仓 {} → 全平仓 close
        - 超过对账间隔 → 触发全量对账（重同步基线）
        """
        current_raw = await self.scraper.fetch_live_positions(trader_id)
        if current_raw is None:
            logger.warning("gate feed: leader %s 接口失败，本轮跳过", trader_id)
            return []
        return await self._poll_with_snapshot(trader_id, current_raw, mode="A")

    async def poll_leaders_many(self, trader_ids: list[str]) -> dict[str, list[FeedEvent]]:
        """★ 页面池并发：批量轮询多个带单员持仓差分。

        一次并发拉取全部持仓快照，再逐个做差分（避免串行 fetch 的 N×往返耗时）。
        返回 {trader_id: [FeedEvent, ...]}，接口失败的交易员为空列表。
        """
        if not trader_ids:
            return {}
        snapshots = await self.scraper.fetch_live_positions_many(trader_ids)
        events_map: dict[str, list[FeedEvent]] = {}
        for tid in trader_ids:
            current_raw = snapshots.get(tid)
            if current_raw is None:
                logger.warning("gate feed: leader %s 接口失败，本轮跳过", tid)
                events_map[tid] = []
                continue
            events_map[tid] = await self._poll_with_snapshot(tid, current_raw, mode="A")
        return events_map

    async def reconcile_leader(self, trader_id: str) -> list[FeedEvent]:
        """★ 全量对账：与当前持仓强制对齐，产出修正事件并重设基线。

        独立于 1s 快速轮询运行，用于兜底漏采/漂移：
        - 无基线 → 建基线，不产出
        - 有基线 → 与最新持仓 diff，产出 open/close 修正
        - 接口失败 → 本轮跳过，不破坏现有基线
        """
        current_raw = await self.scraper.fetch_live_positions(trader_id)
        if current_raw is None:
            logger.warning("gate feed: reconcile %s 接口失败，跳过", trader_id)
            return []
        current = self._filter(current_raw, mode="A")
        state = await self.get_state(trader_id, "A")
        now = time.time()
        if state is None:
            logger.info("gate feed: reconcile %s 无基线，建立基线", trader_id)
            await self.set_state(trader_id, current, now, mode="A")
            return []
        events = self._diff(trader_id, state["pos"], current)
        if events:
            logger.info("gate feed: reconcile %s 修正 %d 个事件", trader_id, len(events))
        await self.set_state(trader_id, current, now, mode="A")
        return events

    async def reconcile_leaders_many(self, trader_ids: list[str]) -> dict[str, list[FeedEvent]]:
        """★ 页面池并发：批量全量对账。

        一次并发拉取全部持仓快照，再逐个与基线对齐产出修正事件（避免串行 fetch）。
        返回 {trader_id: [FeedEvent, ...]}，接口失败的交易员为空列表。
        """
        if not trader_ids:
            return {}
        snapshots = await self.scraper.fetch_live_positions_many(trader_ids)
        events_map: dict[str, list[FeedEvent]] = {}
        for tid in trader_ids:
            current_raw = snapshots.get(tid)
            if current_raw is None:
                logger.warning("gate feed: reconcile %s 接口失败，跳过", tid)
                events_map[tid] = []
                continue
            current = self._filter(current_raw, mode="A")
            state = await self.get_state(tid, "A")
            now = time.time()
            if state is None:
                logger.info("gate feed: reconcile %s 无基线，建立基线", tid)
                await self.set_state(tid, current, now, mode="A")
                events_map[tid] = []
                continue
            events = self._diff(tid, state["pos"], current)
            if events:
                logger.info("gate feed: reconcile %s 修正 %d 个事件", tid, len(events))
            await self.set_state(tid, current, now, mode="A")
            events_map[tid] = events
        return events_map

    # ── 模式2 信号源：跟单账户持仓差分（★按 leader_id 精确对应，只监控自己已跟单的带单员）──
    #   key 用 leader_id（稳定唯一）；快照 {symbol: qty}（跟单数量）；方向 long/short 来自镜像持仓。
    #   ★ 多个带单员镜像仓位混在跟单账户里，必须按 leader_id 隔离，绝不可混淆。
    async def poll_followers_many(
        self, leader_ids: list[str]
    ) -> dict[str, list[FeedEvent]]:
        """批量轮询模式2：拉全部跟单持仓一次，按 leader_id 分组做差分。

        - 整体接口失败（positions=None）→ 该 leader 本轮跳过，不更新基线
        - 首次建立基线 → 不产出（存量持仓不执行）
        - 该 leader 无镜像持仓 {} → 相对基线产出 close（已清仓）
        - open 事件带真实方向 side（镜像仓位 long/short）
        """
        if not leader_ids:
            return {}
        positions_map = await self.scraper.fetch_follower_positions_many(list(leader_ids))
        events_map: dict[str, list[FeedEvent]] = {}
        for lid in leader_ids:
            poses = positions_map.get(lid)
            if poses is None:
                logger.warning("gate feed: follower %s 接口失败，本轮跳过", lid)
                events_map[lid] = []
                continue
            current: dict[str, float] = {p.symbol: p.qty for p in poses}
            current = self._filter(current, mode="B")
            side_map: dict[str, str] = {p.symbol: p.side for p in poses}
            opened_at_map = {p.symbol: p.opened_at for p in poses if p.opened_at is not None}
            events_map[lid] = await self._poll_with_snapshot(
                lid, current, side_map, mode="B", opened_at_map=opened_at_map,
            )
        return events_map

    async def reconcile_followers_many(
        self, leader_ids: list[str]
    ) -> dict[str, list[FeedEvent]]:
        """批量对账模式2：拉全部跟单持仓一次，按 leader_id 与基线对齐产出修正事件。"""
        if not leader_ids:
            return {}
        positions_map = await self.scraper.fetch_follower_positions_many(list(leader_ids))
        events_map: dict[str, list[FeedEvent]] = {}
        for lid in leader_ids:
            poses = positions_map.get(lid)
            if poses is None:
                logger.warning("gate feed: reconcile follower %s 接口失败，跳过", lid)
                events_map[lid] = []
                continue
            current: dict[str, float] = {p.symbol: p.qty for p in poses}
            current = self._filter(current, mode="B")
            side_map: dict[str, str] = {p.symbol: p.side for p in poses}
            opened_at_map = {p.symbol: p.opened_at for p in poses if p.opened_at is not None}
            events_map[lid] = await self._reconcile_with_snapshot(
                lid, current, side_map, mode="B", opened_at_map=opened_at_map,
            )
        return events_map

    async def _fetch_live_metadata(self, trader_id: str) -> tuple[dict[str, str], dict[str, datetime]]:
        """实时持仓方向与源时间（trader/position 接口，公开带单员专用）。

        返回 {sym: long/short}；隐藏持仓（is_hide）/空仓/接口失败 → {}——
        调用方回退 long 默认。★ 2026-08-23 实测：隐藏带单员该接口返回空，
        历史平仓（close_position）虽有方向但无当前状态，无法用于开仓判定。
        """
        try:
            rows = await self.scraper.fetch_leader_positions_live(trader_id)
        except Exception:  # noqa: BLE001 方向补齐失败不阻断差分主流程
            logger.warning("gate feed: live sides %s 拉取失败，open 方向回退 long", trader_id)
            return {}, {}
        sides: dict[str, str] = {}
        opened_at: dict[str, datetime] = {}
        for row in rows or []:
            sym = row.get("symbol")
            s = row.get("side")
            if sym and s in ("long", "short"):
                sides[sym] = s
            raw_at = row.get("opened_at")
            if sym and raw_at:
                try:
                    dt = datetime.fromisoformat(str(raw_at).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    opened_at[sym] = dt.astimezone(timezone.utc)
                except (TypeError, ValueError):
                    pass
        return sides, opened_at

    def _resolve_sides(
        self, trader_id: str, events: list[FeedEvent], current: dict[str, float],
        prev_sides: dict[str, str], side_map: dict[str, str] | None, mode: str,
        live_sides: dict[str, str] | None = None,
    ) -> tuple[list[FeedEvent], dict[str, str]]:
        """事件方向解析（poll 与 reconcile 共用）。

        - open/add/reduce：side_map（模式B镜像）> live_sides（模式A实时补拉）> long
        - close：回查 prev_sides 里"消失仓位原方向"（执行侧据它反向平仓），缺失 > long
        - 返回 (events, 新基线 sides 快照)：live_sides/side_map 覆盖全量方向，
          否则沿用 prev_sides 中仍存在的 symbol（方向对存量不变式成立）。
        """
        has_open = any(e.action == "open" for e in events)
        for ev in events:
            if ev.action in {"open", "add", "reduce"}:
                if side_map:
                    ev.side = side_map.get(ev.symbol, "long")
                elif live_sides:
                    ev.side = live_sides.get(ev.symbol, "long")
            elif ev.action == "close":
                ev.side = prev_sides.get(ev.symbol, "long")
        if side_map:
            new_sides = {sym: side_map.get(sym, "long") for sym in current}
        elif live_sides:
            new_sides = {sym: live_sides.get(sym, "long") for sym in current}
        else:
            new_sides = {sym: prev_sides.get(sym, "long") for sym in current}
        if has_open and mode == "A" and not side_map and not live_sides:
            logger.info("gate feed: %s open 方向未知（隐藏持仓或拉取失败），按 long 处理", trader_id)
        return events, new_sides

    @staticmethod
    def _replace_direction_flips(
        trader_id: str,
        events: list[FeedEvent],
        prev: dict[str, float],
        current: dict[str, float],
        prev_sides: dict[str, str],
        side_map: dict[str, str] | None,
        mode: str,
    ) -> list[FeedEvent]:
        """模式 B 同币种多空反转必须先平旧方向，再开新方向。

        仅比较数量无法发现等量反转；数量改变时还会误判为 add/reduce。用镜像仓位
        返回的真实方向覆盖该 symbol 的普通差分，生成 close + open 两个有序事件。
        """
        if mode != "B" or not side_map or not prev_sides:
            return events
        flipped = {
            sym for sym in set(prev) & set(current)
            if prev_sides.get(sym) in {"long", "short"}
            and side_map.get(sym) in {"long", "short"}
            and prev_sides[sym] != side_map[sym]
        }
        if not flipped:
            return events
        result = [event for event in events if event.symbol not in flipped]
        for sym in sorted(flipped):
            result.append(FeedEvent(trader_id=trader_id, symbol=sym, action="close"))
            result.append(FeedEvent(
                trader_id=trader_id, symbol=sym, action="open", percent=current[sym],
            ))
        return result

    async def _poll_with_snapshot(
        self, trader_id: str, current_raw: dict[str, float], side_map: dict[str, str] | None = None,
        mode: str = "A", opened_at_map: dict[str, datetime] | None = None,
    ) -> list[FeedEvent]:
        """给定持仓快照做差分（poll 路径共用，side_map 提供 open 方向）。

        ★ 模式A open 方向真实化（2026-08-23）：占比接口无方向，open 事件实时补拉
          trader/position（仅出 open 事件时才拉，稀有事件成本 ~1.4s/次）取真实
          long/short；隐藏带单员返回空 → 保持 long（公开渠道无当前方向）。
        """
        current = self._filter(current_raw, mode=mode)
        state = await self.get_state(trader_id, mode)
        now = time.time()
        events: list[FeedEvent] = []
        if state is None:
            logger.info("gate feed: %s 首次建立基线（%d 个存量持仓跳过）", trader_id, len(current))
            baseline_sides = (
                {sym: side_map.get(sym, "long") for sym in current} if side_map else None
            )
            await self.set_state(
                trader_id, current, now, mode=mode, sides=baseline_sides,
            )
            return []
        prev = state["pos"]
        prev_sides = state.get("sides") or {}
        events = self._diff(trader_id, prev, current, emit_size_changes=(mode == "B"))
        events = self._replace_direction_flips(
            trader_id, events, prev, current, prev_sides, side_map, mode,
        )
        live_sides: dict[str, str] = {}
        if mode == "A" and not side_map and any(e.action == "open" for e in events):
            live_sides, live_opened_at = await self._fetch_live_metadata(trader_id)
            opened_at_map = {**(opened_at_map or {}), **live_opened_at}
        for ev in events:
            if ev.action == "open" and opened_at_map and ev.symbol in opened_at_map:
                ev.at = opened_at_map[ev.symbol]
        events, new_sides = self._resolve_sides(
            trader_id, events, current, prev_sides, side_map, mode, live_sides,
        )
        prev_ts = state.get("ts")
        if prev_ts and (now - prev_ts) > self.reconcile_interval:
            logger.warning(
                "gate feed: %s 距上次同步 %.0fs 超过对账间隔 %ds，执行全量对账",
                trader_id, now - prev_ts, self.reconcile_interval,
            )
        await self.set_state(trader_id, current, now, mode=mode, sides=new_sides)
        return events

    async def _reconcile_with_snapshot(
        self, trader_id: str, current_raw: dict[str, float], side_map: dict[str, str] | None = None,
        mode: str = "A", opened_at_map: dict[str, datetime] | None = None,
    ) -> list[FeedEvent]:
        """全量对账差分（reconcile 路径共用，side_map 提供 open 方向）。"""
        current = self._filter(current_raw, mode=mode)
        state = await self.get_state(trader_id, mode)
        now = time.time()
        if state is None:
            logger.info("gate feed: reconcile %s 无基线，建立基线", trader_id)
            baseline_sides = (
                {sym: side_map.get(sym, "long") for sym in current} if side_map else None
            )
            await self.set_state(
                trader_id, current, now, mode=mode, sides=baseline_sides,
            )
            return []
        prev = state["pos"]
        prev_sides = state.get("sides") or {}
        events = self._diff(
            trader_id, prev, current, emit_size_changes=(mode == "B")
        )
        events = self._replace_direction_flips(
            trader_id, events, prev, current, prev_sides, side_map, mode,
        )
        live_sides: dict[str, str] = {}
        if mode == "A" and not side_map and any(e.action == "open" for e in events):
            live_sides, live_opened_at = await self._fetch_live_metadata(trader_id)
            opened_at_map = {**(opened_at_map or {}), **live_opened_at}
        for ev in events:
            if ev.action == "open" and opened_at_map and ev.symbol in opened_at_map:
                ev.at = opened_at_map[ev.symbol]
        events, new_sides = self._resolve_sides(
            trader_id, events, current, prev_sides, side_map, mode, live_sides,
        )
        if events:
            logger.info("gate feed: reconcile %s 修正 %d 个事件", trader_id, len(events))
        await self.set_state(trader_id, current, now, mode=mode, sides=new_sides)
        return events
