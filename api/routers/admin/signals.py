# admin/signals 路由（M5 T5.4：策略管理 - 列表/上架/下架/暂停；G04 force 留痕）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.core.errors import NotFoundError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.signal import Strategy, Trader
from api.services.audit.service import AuditService
from api.services.strategies.service import StrategyService

router = APIRouter(prefix="/signals", tags=["admin-signals"])


class StatusIn(BaseModel):
    status: str  # listed / paused / delisted


class GrayIn(BaseModel):
    gray_pct: int  # 0-100


class ForceListIn(BaseModel):
    trader_id: int
    display_name: str
    style: str = "trend"
    risk_rating: str = "mid"
    force: bool = True
    force_reason: str


# ── 策略级风控（Redis 可配，键 risk:strategy:{id}:*，默认单笔 2000 / 回撤 25%）──
STRATEGY_RISK_DEFAULTS = {
    "max_order_notional": 2000.0,
    "max_drawdown_pct": 25.0,
}


def _redis():
    from redis import Redis

    from api.core.config import get_settings

    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def get_strategy_risk(strategy_id: int) -> dict:
    """读取某策略级风控配置（未单独配置时返回默认值 + opt=None）。"""
    r = _redis()
    out = {}
    for key, default in STRATEGY_RISK_DEFAULTS.items():
        raw = r.get(f"risk:strategy:{strategy_id}:{key}")
        if raw is None:
            out[key] = default
            out[f"{key}_set"] = False
        else:
            try:
                out[key] = float(raw)
            except ValueError:
                out[key] = default
            out[f"{key}_set"] = True
    return out


@router.get("/pending")
async def pending_list(db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """待选池：无 Strategy 的 Trader + 最新画像快照。"""
    from sqlalchemy import select

    from api.models.signal import Trader, TraderProfile

    # 简化：直接查最新画像（join 最新一条）
    items = []
    for trader in (await db.execute(select(Trader).outerjoin(Strategy, Strategy.trader_id == Trader.id).where(Strategy.id.is_(None)).order_by(Trader.id.desc()).limit(100))).scalars().all():
        profile = (
            await db.execute(
                select(TraderProfile)
                .where(TraderProfile.trader_id == trader.id)
                .order_by(TraderProfile.snapshot_date.desc())
                .limit(1)
            )
        ).scalars().first()
        items.append(
            {
                "id": trader.id,
                "exchange": trader.exchange,
                "trader_id": trader.trader_id,
                "name": trader.trader_id,
                "roi_7d": profile.roi_7d if profile else 0,
                "roi_30d": profile.roi_30d if profile else 0,
                "roi_all": profile.roi_all if profile else 0,
                "win_rate_all": profile.win_rate_all if profile else 0,
                "max_drawdown": profile.max_drawdown if profile else 0,
                "trading_days": profile.trading_days if profile else 0,
                "followers": trader.followers or 0,
            }
        )
    return {"items": items}


@router.get("")
async def list_strategies(
    status: str = Query(""),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from sqlalchemy import select

    from api.models.signal import TraderProfile

    stmt = select(Strategy).order_by(Strategy.id.desc())
    if status:
        stmt = stmt.where(Strategy.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    items = []
    for s in rows:
        trader = await db.get(Trader, s.trader_id)
        profile = (
            await db.execute(
                select(TraderProfile)
                .where(TraderProfile.trader_id == s.trader_id)
                .order_by(TraderProfile.snapshot_date.desc())
                .limit(1)
            )
        ).scalars().first()
        risk = get_strategy_risk(s.id)
        items.append(
            {
                "id": s.id,
                "trader_id": s.trader_id,
                "exchange": s.source_exchange,
                "display_name": s.display_name,
                "style": s.style,
                "risk_rating": s.risk_rating,
                "status": s.status,
                "followers": trader.followers if trader else 0,
                "roi_7d": profile.roi_7d if profile else 0,
                "roi_30d": profile.roi_30d if profile else 0,
                "roi_all": profile.roi_all if profile else 0,
                "win_rate_30d": profile.win_rate_30d if profile else 0,
                "win_rate_all": profile.win_rate_all if profile else 0,
                "max_drawdown": profile.max_drawdown if profile else 0,
                "trading_days": profile.trading_days if profile else 0,
                # ★ 策略级风控（Redis 可配，opt 为 None 表示未单独配置）
                "risk": risk,
            }
        )
    return {"items": items}


@router.post("")
async def force_list(body: ForceListIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ G04：强制上架（跳过门槛，必须填理由留痕 audit-log）。"""
    svc = StrategyService(db)
    strategy, gate = await svc.add_strategy(
        trader_id=body.trader_id,
        display_name=body.display_name,
        style=body.style,
        risk_rating=body.risk_rating,
        exchange="gate",
        force=True,
        force_reason=body.force_reason,
        actor_id=admin["id"],
    )
    # ★ M6 T5.19：strategy.update 实时推送
    from api.ws.hub import hub

    await hub.broadcast(
        "strategy.update",
        {"strategy_id": strategy.id, "display_name": strategy.display_name, "status": strategy.status, "action": "listed"},
    )
    return {"id": strategy.id, "status": strategy.status, "gate_passed": True, "forced": True, "failures": gate.failures}


@router.patch("/{strategy_id}/status")
async def update_status(strategy_id: int, body: StatusIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    svc = StrategyService(db)
    strategy = await svc.update_status(strategy_id, body.status, actor_id=admin["id"])
    # ★ M6 T5.19：strategy.update 实时推送
    from api.ws.hub import hub

    await hub.broadcast(
        "strategy.update",
        {"strategy_id": strategy.id, "display_name": strategy.display_name, "status": strategy.status, "action": "status"},
    )
    return {"id": strategy.id, "status": strategy.status}


@router.patch("/{strategy_id}/gray")
async def set_gray(strategy_id: int, body: GrayIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ M6 T6.1 灰度发布：设置放量比例（0-100），audit 留痕。"""
    from api.core.errors import ValidationError


    if not 0 <= body.gray_pct <= 100:
        raise ValidationError("gray_pct 必须在 0-100")
    strategy = await db.get(Strategy, strategy_id)
    if strategy is None:
        raise NotFoundError("策略不存在")
    before = strategy.gray_pct
    strategy.gray_pct = body.gray_pct
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="strategy.gray",
        target_type="strategy", target_id=str(strategy_id),
        before={"gray_pct": before}, after={"gray_pct": strategy.gray_pct},
    )
    return {"id": strategy_id, "gray_pct": strategy.gray_pct}


class StrategyRiskIn(BaseModel):
    max_order_notional: float | None = None
    max_drawdown_pct: float | None = None


class SyncIn(BaseModel):
    trader_id: str | None = None  # 指定同步单个带单员；空则全量（后台异步）


@router.post("/sync")
async def sync_profiles(body: SyncIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ 同步画像（后台「同步画像」按钮）：单带单员同步执行；全量投递 Celery 后台。"""
    from api.core.errors import ValidationError

    from api.workers.tasks_profile import run_sync_one_sync

    await AuditService(db).log(
        actor_id=admin["id"], action="strategy.sync_profile",
        target_type="strategy", target_id=body.trader_id or "all",
        after={"trader_id": body.trader_id},
    )
    if body.trader_id:
        result = run_sync_one_sync(body.trader_id)
        return {"mode": "one", "result": result}
    # 全量：优先投递 Celery 后台任务；broker 不可用时降级同步执行 top 50
    try:
        from api.workers.celery_app import celery_app

        task = celery_app.send_task("profile.sync_daily", kwargs={"limit": 50})
        return {"mode": "all", "async": True, "task_id": getattr(task, "id", None)}
    except Exception:  # noqa: BLE001 broker 不可用 → 同步降级
        import asyncio

        from api.workers.tasks_profile import run_sync_daily

        count = asyncio.run(run_sync_daily(50))
        return {"mode": "all", "async": False, "count": count, "note": "broker 不可用，已同步降级"}


@router.get("/{strategy_id}/risk")
async def get_risk(strategy_id: int, db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """★ 策略级风控参数（Redis 可配，未配置返回默认值）。"""
    strategy = await db.get(Strategy, strategy_id)
    if strategy is None:
        raise NotFoundError("策略不存在")
    return {"id": strategy_id, **get_strategy_risk(strategy_id)}


@router.patch("/{strategy_id}/risk")
async def set_risk(strategy_id: int, body: StrategyRiskIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ 更新策略级风控参数（audit 留痕）。"""
    from api.core.errors import ValidationError

    strategy = await db.get(Strategy, strategy_id)
    if strategy is None:
        raise NotFoundError("策略不存在")
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise ValidationError("至少提供一个参数")
    r = _redis()
    before = get_strategy_risk(strategy_id)
    for key, value in payload.items():
        if key not in STRATEGY_RISK_DEFAULTS:
            raise ValidationError(f"未知参数: {key}")
        if value < 0:
            raise ValidationError(f"{key} 不能为负")
        r.set(f"risk:strategy:{strategy_id}:{key}", str(value))
    await AuditService(db).log(
        actor_id=admin["id"], action="strategy.risk_update",
        target_type="strategy", target_id=str(strategy_id),
        before=before, after=payload,
    )
    return {"id": strategy_id, **get_strategy_risk(strategy_id)}
