# strategies 路由（M2 T2.5 待选池 / T2.6 已添加池 + G04 / T2.9-T2.11 前端）
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.deps import DbDep, get_current_user
from api.services.strategies.service import StrategyService

router = APIRouter(prefix="/strategies", tags=["strategies"])


# ── Schemas ──
class StrategyCreate(BaseModel):
    trader_id: int
    display_name: str = Field(min_length=1, max_length=64)
    style: Literal["trend", "range", "momentum"] = "trend"
    risk_rating: Literal["low", "mid", "high"] = "mid"
    exchange: str = "gate"
    force: bool = False
    force_reason: str | None = Field(default=None, max_length=200)


class StrategyStatusUpdate(BaseModel):
    status: Literal["listed", "paused", "delisted"]


# ── 待选池（T2.5 后台）──
@router.get("/pending")
async def list_pending(
    exchange: str = "gate",
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbDep = None,
    _user: int = Depends(get_current_user),
) -> dict:
    svc = StrategyService(db)
    rows, total = await svc.list_pending_traders(exchange, keyword, page, size)
    return {"items": rows, "total": total, "page": page, "size": size}


# ── 已添加池（T2.6 后台 + 前端策略广场）──
@router.get("")
async def list_strategies(
    exchange: str | None = None,
    status: str | None = None,
    style: str | None = None,
    risk_rating: str | None = None,
    sort: str = "roi_30d",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbDep = None,
) -> dict:
    """策略广场（公开，无需登录）。"""
    svc = StrategyService(db)
    rows, _ = await svc.list_listed_strategies(exchange, status)

    # 前端筛选/排序（T2.9），在【全量】基础上进行以得到正确 total
    if style:
        rows = [r for r in rows if r["style"] == style]
    if risk_rating:
        rows = [r for r in rows if r["risk_rating"] == risk_rating]
    if sort in ("roi_7d", "roi_30d", "roi_90d", "roi_all", "win_rate_all", "followers"):
        rows.sort(key=lambda r: r.get(sort, 0), reverse=True)
    total = len(rows)
    start = (page - 1) * size
    return {"items": rows[start : start + size], "total": total, "page": page, "size": size}


# ── 上架（★ G04）──
@router.post("")
async def add_strategy(
    body: StrategyCreate,
    db: DbDep = None,
    user_id: int = Depends(get_current_user),
) -> dict:
    svc = StrategyService(db)
    strategy, gate = await svc.add_strategy(
        trader_id=body.trader_id,
        display_name=body.display_name,
        style=body.style,
        risk_rating=body.risk_rating,
        exchange=body.exchange,
        force=body.force,
        force_reason=body.force_reason,
        actor_id=user_id,
    )
    return {
        "id": strategy.id,
        "status": strategy.status,
        "gate_passed": gate.ok or gate.forced,
        "failures": gate.failures,
        "forced": gate.forced,
    }


# ── 状态变更（下架/暂停）──
@router.patch("/{strategy_id}/status")
async def update_status(
    strategy_id: int,
    body: StrategyStatusUpdate,
    db: DbDep = None,
    user_id: int = Depends(get_current_user),
) -> dict:
    svc = StrategyService(db)
    strategy = await svc.update_status(strategy_id, body.status, actor_id=user_id)
    return {"id": strategy.id, "status": strategy.status}


# ── 策略详情（T2.10/T2.11 ★ G21 画像兜底）──
@router.get("/{strategy_id}")
async def strategy_detail(strategy_id: int, db: DbDep = None) -> dict:
    svc = StrategyService(db)
    return await svc.get_strategy_detail(strategy_id)


# ── 收益曲线（M6 前端补全）──
@router.get("/{strategy_id}/equity")
async def strategy_equity(strategy_id: int, db: DbDep = None) -> dict:
    svc = StrategyService(db)
    return await svc.get_equity_curve(strategy_id)
