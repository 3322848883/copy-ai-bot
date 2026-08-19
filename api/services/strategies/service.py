# strategies 模块（M2 T2.6：策略包装 + ★G04 门槛校验）
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.errors import ConflictError, NotFoundError, ValidationError
from api.models.audit import AuditEvent
from api.models.signal import Strategy, Trader, TraderProfile

logger = logging.getLogger("signal-saas.strategies")

# ★ G04：带单员上架门槛
G04_MIN_WIN_RATE = 55.0   # 胜率 ≥ 55%
G04_MAX_DRAWDOWN = 30.0   # 回撤 ≤ 30%
G04_MIN_TRADING_DAYS = 30  # 天数 ≥ 30


def format_display_name(nick: str | None, trader_id: str) -> str:
    """★ 统一信号源策略名称标准：昵称（id），如「复利如慢牛（32801）」。"""
    nick = (nick or "").strip()
    if not nick:
        return trader_id
    return f"{nick}（{trader_id}）"


class TraderSelectionPolicy:
    """★ G04 带单员门槛校验：不达标禁止上架；force=true 可跳过但需理由 + audit-log。"""

    def __init__(self, win_rate: float, max_drawdown: float, trading_days: int) -> None:
        self.win_rate = win_rate
        self.max_drawdown = max_drawdown
        self.trading_days = trading_days

    @property
    def passed(self) -> bool:
        return (
            self.win_rate >= G04_MIN_WIN_RATE
            and self.max_drawdown <= G04_MAX_DRAWDOWN
            and self.trading_days >= G04_MIN_TRADING_DAYS
        )

    def failures(self) -> list[str]:
        out: list[str] = []
        if self.win_rate < G04_MIN_WIN_RATE:
            out.append(f"胜率 {self.win_rate}% < 55%")
        if self.max_drawdown > G04_MAX_DRAWDOWN:
            out.append(f"回撤 {self.max_drawdown}% > 30%")
        if self.trading_days < G04_MIN_TRADING_DAYS:
            out.append(f"交易天数 {self.trading_days} < 30")
        return out


@dataclass
class GateResult:
    ok: bool
    failures: list[str]
    forced: bool = False


class StrategyService:
    """策略包装：待选池 Trader → 已添加池 Strategy（★ G04 门槛）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── 待选池查询（T2.5）──
    async def list_pending_traders(
        self, exchange: str = "gate", keyword: str | None = None, page: int = 1, size: int = 20
    ) -> tuple[list[dict], int]:
        """已爬取但未上架的带单员（全量爬取数据 + 分页搜索）。"""
        traders = (await self.db.execute(select(Trader).where(Trader.exchange == exchange))).scalars().all()
        listed_ids = set(
            (await self.db.execute(select(Strategy.trader_id))).scalars().all()
        )
        profiles = {
            p.trader_id: p
            for p in (await self.db.execute(select(TraderProfile))).scalars().all()
        }

        rows: list[dict] = []
        for t in traders:
            if t.id in listed_ids:
                continue  # 已添加 → 不属于待选池
            p = profiles.get(t.id)
            if keyword and keyword.lower() not in t.trader_id.lower():
                continue
            rows.append(self._trader_dict(t, p))
        total = len(rows)
        start = (page - 1) * size
        return rows[start : start + size], total

    async def list_listed_strategies(
        self, exchange: str | None = None, status: str | None = None
    ) -> tuple[list[dict], int]:
        """已添加池策略（上架后）。返回全量列表 + 总数，筛选/排序/分页由路由层完成。"""
        stmt = select(Strategy).order_by(Strategy.id.desc())
        if exchange:
            stmt = stmt.where(Strategy.source_exchange == exchange)
        if status:
            stmt = stmt.where(Strategy.status == status)
        strategies = (await self.db.execute(stmt)).scalars().all()

        rows: list[dict] = []
        for s in strategies:
            trader = await self.db.get(Trader, s.trader_id)
            profile = (
                await self.db.execute(
                    select(TraderProfile)
                    .where(TraderProfile.trader_id == s.trader_id)
                    .order_by(TraderProfile.snapshot_date.desc())
                    .limit(1)
                )
            ).scalars().first()
            rows.append(self._strategy_dict(s, trader, profile))
        return rows, len(rows)

    # ── ★ G04 上架 ──
    async def add_strategy(
        self,
        trader_id: int,
        display_name: str,
        style: str,
        risk_rating: str,
        exchange: str = "gate",
        force: bool = False,
        force_reason: str | None = None,
        actor_id: int | None = None,
    ) -> tuple[Strategy, GateResult]:
        """包装 Trader 为 Strategy。★ G04：门槛校验，force 可跳过但需理由 + audit-log。"""
        trader = await self.db.get(Trader, trader_id)
        if trader is None:
            raise NotFoundError("带单员不存在")

        existing = await self.db.scalar(select(Strategy).where(Strategy.trader_id == trader_id))
        if existing:
            raise ConflictError("该带单员已在已添加池")

        profile = (
            await self.db.execute(
                select(TraderProfile)
                .where(TraderProfile.trader_id == trader_id)
                .order_by(TraderProfile.snapshot_date.desc())
                .limit(1)
            )
        ).scalars().first()

        win_rate = profile.win_rate_all if profile else 0.0
        drawdown = profile.max_drawdown if profile else 0.0
        days = profile.trading_days if profile else 0
        policy = TraderSelectionPolicy(win_rate, drawdown, days)

        gate = GateResult(ok=policy.passed, failures=[] if policy.passed else policy.failures())
        if not policy.passed and not force:
            raise ValidationError("带单员未达上架门槛: " + "; ".join(policy.failures()))

        strategy = Strategy(
            trader_id=trader_id,
            source_exchange=exchange,
            # ★ 统一命名标准：昵称（id），忽略前端自定义名
            display_name=format_display_name(trader.name, trader.trader_id),
            style=style,
            risk_rating=risk_rating,
            status="listed",
        )
        self.db.add(strategy)
        if force:
            gate.forced = True
            # audit-log 强制跳过留痕
            self.db.add(
                AuditEvent(
                    actor_id=actor_id,
                    action="strategy.force_list",
                    target_type="strategy",
                    target_id=str(trader_id),
                    before=None,
                    after=json.dumps({"failures": policy.failures(), "reason": force_reason or ""}),
                    reason=force_reason or "",
                    created_at=datetime.now(timezone.utc),
                )
            )
        await self.db.commit()
        await self.db.refresh(strategy)
        return strategy, gate

    async def update_status(self, strategy_id: int, status: str, actor_id: int | None = None) -> Strategy:
        """下架 / 暂停 / 恢复。"""
        if status not in ("listed", "paused", "delisted"):
            raise ValidationError("status 非法")
        strategy = await self.db.get(Strategy, strategy_id)
        if strategy is None:
            raise NotFoundError("策略不存在")
        strategy.status = status
        self.db.add(
            AuditEvent(
                actor_id=actor_id,
                action=f"strategy.{status}",
                target_type="strategy",
                target_id=str(strategy_id),
                before=json.dumps({"status": "listed" if status != "listed" else "paused"}),
                after=json.dumps({"status": status}),
                created_at=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()
        await self.db.refresh(strategy)
        return strategy

    # ── ★ 完全自动：我账户跟单的交易员 → 策略广场展示项 ──
    async def ensure_followed_strategy(self, trader_id: int, display_name: str, exchange: str = "gate") -> Strategy:
        """确保「我账户跟单的交易员」有 listed 策略（完全自动，跳过 G04 门槛）。

        策略广场只展示我账户跟单的交易员：跟单了谁就展示谁，无需后台审核。
        """
        trader = await self.db.get(Trader, trader_id)
        std_name = format_display_name(trader.name if trader else None, trader.trader_id if trader else str(trader_id))
        existing = await self.db.scalar(select(Strategy).where(Strategy.trader_id == trader_id))
        if existing:
            if existing.display_name != std_name:
                existing.display_name = std_name
            # ★ 重新跟单：模式2 管辖恢复（此前被 delist_unfollowed 下架的 B 类）
            if existing.source != "B":
                existing.source = "B"
            if existing.status != "listed":
                existing.status = "listed"
                await self.db.flush()
            return existing
        strategy = Strategy(
            trader_id=trader_id,
            source_exchange=exchange,
            display_name=std_name,
            style="trend",
            risk_rating="mid",
            status="listed",
            source="B",
        )
        self.db.add(strategy)
        await self.db.flush()
        return strategy

    async def delist_unfollowed(self, followed_trader_ids: set[int]) -> int:
        """把不再跟单的交易员策略自动下架（策略广场只保留我账户跟单的交易员）。

        ★ 只下架 source='B'（跟单同步自动上架）的策略；'A'（公开广场 G04 审核上架）
        是管理员人工决策，跟单关系变化不得自动下架——否则模式1 上架活不过一个同步周期。
        """
        strategies = (
            await self.db.execute(
                select(Strategy).where(Strategy.status == "listed", Strategy.source == "B")
            )
        ).scalars().all()
        count = 0
        for s in strategies:
            if s.trader_id not in followed_trader_ids:
                s.status = "delisted"
                count += 1
        if count:
            await self.db.flush()
        return count

    # ── 策略详情（T2.10/T2.11 ★ G21 缓存兜底）──
    async def get_strategy_detail(self, strategy_id: int) -> dict:
        """策略详情 + 画像（★ G21：is_stale / placeholder 兜底）。"""
        strategy = await self.db.get(Strategy, strategy_id)
        if strategy is None:
            raise NotFoundError("策略不存在")
        trader = await self.db.get(Trader, strategy.trader_id)

        today = None
        profile = (
            await self.db.execute(
                select(TraderProfile)
                .where(TraderProfile.trader_id == strategy.trader_id)
                .order_by(TraderProfile.snapshot_date.desc())
                .limit(1)
            )
        ).scalars().first()

        # ★ G21：画像兜底
        from datetime import date

        today = date.today()
        if profile is None:
            profile_state = {"is_stale": False, "placeholder": True}
            profile_payload = None
        elif profile.snapshot_date == today:
            profile_state = {"is_stale": False, "placeholder": False}
            profile_payload = profile
        else:
            # 昨日数据 + 标注
            profile_state = {"is_stale": True, "placeholder": False}
            profile_payload = profile

        data = self._strategy_dict(strategy, trader, profile_payload)
        data["profile_state"] = profile_state
        data["positions"] = []  # M3 接入实时持仓
        data["recent_orders"] = []  # M3 接入交易记录
        return data

    # ── 收益曲线（M6 前端补全：基于每日画像快照 roi_all 生成净值曲线）──
    async def get_equity_curve(self, strategy_id: int) -> dict:
        """返回按日期升序的累计收益曲线（%），支持 7d/30d/90d/历史 四档。"""
        strategy = await self.db.get(Strategy, strategy_id)
        if strategy is None:
            raise NotFoundError("策略不存在")
        rows = (
            await self.db.execute(
                select(TraderProfile)
                .where(TraderProfile.trader_id == strategy.trader_id)
                .order_by(TraderProfile.snapshot_date.asc())
            )
        ).scalars().all()
        if not rows:
            return {"points": [], "ranges": {"7d": [], "30d": [], "90d": [], "all": []}}

        points = [
            {"date": p.snapshot_date.isoformat(), "value": round(p.roi_all, 2)}
            for p in rows
        ]
        n = len(points)
        ranges = {
            "7d": points[-7:],
            "30d": points[-30:],
            "90d": points[-90:],
            "all": points,
        }
        return {"points": points, "ranges": ranges, "total_points": n}

    # ── helpers ──
    def _trader_dict(self, t: Trader, p: TraderProfile | None) -> dict:
        return {
            "id": t.id,
            "exchange": t.exchange,
            "trader_id": t.trader_id,
            "name": format_display_name(t.name, t.trader_id),
            "roi_7d": p.roi_7d if p else 0,
            "roi_30d": p.roi_30d if p else 0,
            "roi_90d": p.roi_90d if p else 0,
            "roi_all": p.roi_all if p else 0,
            "win_rate_30d": p.win_rate_30d if p else 0,
            "win_rate_all": p.win_rate_all if p else 0,
            "max_drawdown": p.max_drawdown if p else 0,
            "trading_days": p.trading_days if p else 0,
            "followers": 0,
        }

    def _strategy_dict(self, s: Strategy, t: Trader | None, p: TraderProfile | None) -> dict:
        return {
            "id": s.id,
            "trader_id": s.trader_id,
            "exchange": s.source_exchange,
            "display_name": s.display_name,
            "style": s.style,
            "risk_rating": s.risk_rating,
            "status": s.status,
            "roi_7d": p.roi_7d if p else 0,
            "roi_30d": p.roi_30d if p else 0,
            "roi_90d": p.roi_90d if p else 0,
            "roi_all": p.roi_all if p else 0,
            "win_rate_30d": p.win_rate_30d if p else 0,
            "win_rate_all": p.win_rate_all if p else 0,
            "max_drawdown": p.max_drawdown if p else 0,
            "trading_days": p.trading_days if p else 0,
            "followers": 0,
            "trader_id_external": t.trader_id if t else None,
        }
