# dashboard 路由（M6 P0：首页数据看板）
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import DbDep, get_current_user
from api.services.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    """首页数据看板：4 指标卡 + 新手引导 + 我的跟单 + 实时行情 + 最近订单。"""
    return await DashboardService(db).get_dashboard(user_id)
