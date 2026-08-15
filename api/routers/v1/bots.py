# bots 路由（M3 T3.2/T3.9：跟单机器人 CRUD + 我的跟单）
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.deps import DbDep, get_current_user
from api.services.bots.service import BotService

router = APIRouter(prefix="/bots", tags=["bots"])


class BotCreate(BaseModel):
    strategy_id: int
    exchange: str
    api_key_id: int
    amount_mode: Literal["fixed", "percent"] = "percent"
    fixed_amount_usdt: float | None = Field(default=None, gt=0)
    percent: float | None = Field(default=20.0, gt=0, le=100)
    leverage: int = Field(default=10, ge=1, le=125)
    margin_mode: Literal["isolated", "cross"] = "isolated"  # ★ G07
    max_total_position_usdt: float = Field(default=10_000.0, gt=0)
    paper: bool = False  # ★ M6 T6.2 沙箱模拟盘


class BotStatusUpdate(BaseModel):
    status: Literal["active", "paused", "stopped"]


class BotConfigUpdate(BaseModel):
    """M6 前端补全：修改机器人配置（全部可选，仅传变化的字段）。"""
    percent: float | None = Field(default=None, gt=0, le=100)
    leverage: int | None = Field(default=None, ge=1, le=125)
    margin_mode: Literal["isolated", "cross"] | None = None
    max_total_position_usdt: float | None = Field(default=None, gt=0)
    amount_mode: Literal["fixed", "percent"] | None = None
    fixed_amount_usdt: float | None = Field(default=None, gt=0)


@router.post("")
async def create_bot(body: BotCreate, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = BotService(db)
    bot = await svc.create(
        user_id=user_id,
        strategy_id=body.strategy_id,
        exchange=body.exchange,
        api_key_id=body.api_key_id,
        amount_mode=body.amount_mode,
        fixed_amount_usdt=body.fixed_amount_usdt,
        percent=body.percent,
        leverage=body.leverage,
        margin_mode=body.margin_mode,
        max_total_position_usdt=body.max_total_position_usdt,
        paper=body.paper,
    )
    return {"id": bot.id, "status": bot.status, "paper": bot.paper}


@router.get("")
async def list_bots(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = BotService(db)
    return {"items": await svc.list(user_id)}


@router.patch("/{bot_id}/status")
async def update_status(bot_id: int, body: BotStatusUpdate, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = BotService(db)
    bot = await svc.update_status(user_id, bot_id, body.status)
    return {"id": bot.id, "status": bot.status}


@router.patch("/{bot_id}")
async def update_config(bot_id: int, body: BotConfigUpdate, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    """M6 前端补全：修改机器人配置。"""
    svc = BotService(db)
    bot = await svc.update(
        user_id, bot_id,
        percent=body.percent, leverage=body.leverage, margin_mode=body.margin_mode,
        max_total_position_usdt=body.max_total_position_usdt,
        amount_mode=body.amount_mode, fixed_amount_usdt=body.fixed_amount_usdt,
    )
    return {"id": bot.id, "status": bot.status, "percent": bot.percent, "leverage": bot.leverage,
            "margin_mode": bot.margin_mode, "max_total_position_usdt": bot.max_total_position_usdt}


@router.delete("/{bot_id}")
async def delete_bot(bot_id: int, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = BotService(db)
    await svc.delete(user_id, bot_id)
    return {"deleted": True}


@router.get("/{bot_id}/orders")
async def bot_orders(bot_id: int, limit: int = Query(20, ge=1, le=100), db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = BotService(db)
    return {"items": await svc.get_orders(user_id, bot_id, limit)}


@router.get("/{bot_id}/positions")
async def bot_positions(bot_id: int, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = BotService(db)
    return {"items": await svc.get_positions(user_id, bot_id)}
