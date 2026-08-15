# admin/risk 路由（M5 T5.8：风控面板 - 紧急制动 + 每日亏损限额 + 刷单检测）
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.core.config import get_settings
from api.deps import DbDep, get_current_admin, require_admin
from api.services.audit.service import AuditService

router = APIRouter(prefix="/risk", tags=["admin-risk"])

# Redis 键（全局风控配置，跟单引擎/提现引擎运行时读取）
KEY_EMERGENCY_STOP = "risk:emergency_stop"
KEY_DAILY_LOSS_LIMIT = "risk:daily_loss_limit"


class EmergencyStopIn(BaseModel):
    enabled: bool


class DailyLossIn(BaseModel):
    limit_usdt: float = Field(gt=0)


class AbuseIn(BaseModel):
    inviter_id: int


def _redis():
    from redis import Redis

    return Redis.from_url(get_settings().redis_url, decode_responses=True)


@router.get("/panel")
async def panel(db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    r = _redis()
    emergency = r.get(KEY_EMERGENCY_STOP) == "1"
    daily_limit = float(r.get(KEY_DAILY_LOSS_LIMIT) or -1000.0)
    return {
        "emergency_stop": emergency,
        "daily_loss_limit_usdt": daily_limit,
        "note": "刷单检测按邀请人维度，见 referral service",
    }


@router.post("/emergency-stop")
async def set_emergency_stop(body: EmergencyStopIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ 全局紧急制动：开启后所有 OPEN/ADD 跟单拒绝，仅放行平仓。"""
    r = _redis()
    before = r.get(KEY_EMERGENCY_STOP)
    r.set(KEY_EMERGENCY_STOP, "1" if body.enabled else "0")
    await AuditService(db).log(
        actor_id=admin["id"], action="risk.emergency_stop",
        target_type="risk", target_id="global",
        before={"enabled": before == "1"}, after={"enabled": body.enabled},
    )
    return {"emergency_stop": body.enabled}


@router.post("/daily-loss-limit")
async def set_daily_loss(body: DailyLossIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    r = _redis()
    r.set(KEY_DAILY_LOSS_LIMIT, str(body.limit_usdt))
    await AuditService(db).log(
        actor_id=admin["id"], action="risk.daily_loss_limit",
        target_type="risk", target_id="global",
        after={"limit_usdt": body.limit_usdt},
    )
    return {"daily_loss_limit_usdt": body.limit_usdt}


@router.post("/abuse-check")
async def abuse_check(body: AbuseIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """手动触发刷单检测（★ T4.9）。"""
    from api.services.referral.service import ReferralService

    svc = ReferralService(db)
    flagged = await svc.detect_batch_abuse(body.inviter_id)
    await AuditService(db).log(
        actor_id=admin["id"], action="risk.abuse_check",
        target_type="user", target_id=str(body.inviter_id),
        after={"flagged": flagged},
    )
    return {"inviter_id": body.inviter_id, "flagged": flagged}
