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
