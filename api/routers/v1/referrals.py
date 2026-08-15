# referrals 路由（M4 T4.5：邀请码 + 邀请列表 + 刷单检测）
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import DbDep, get_current_user
from api.services.referral.service import ReferralService

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/code")
async def my_code(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = ReferralService(db)
    code = await svc.get_or_create_code(user_id)
    return {"code": code}


@router.get("/invites")
async def my_invites(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = ReferralService(db)
    return {"items": await svc.list_invites(user_id)}


@router.get("/risk")
async def abuse_check(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = ReferralService(db)
    flagged = await svc.detect_batch_abuse(user_id)
    return {"risk_flag": flagged}


@router.get("/stats")
async def my_stats(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    """M6 前端补全：邀请中心统计卡。"""
    svc = ReferralService(db)
    return await svc.get_stats(user_id)
