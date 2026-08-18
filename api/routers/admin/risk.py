# admin/risk 路由（M5 T5.8：风控面板 - 紧急制动 + 每日亏损限额 + 刷单检测）
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.core.config import get_settings
from api.core.errors import ValidationError
from api.deps import DbDep, get_current_admin, require_admin
from api.services.audit.service import AuditService

router = APIRouter(prefix="/risk", tags=["admin-risk"])

# Redis 键（全局风控配置，跟单引擎/提现引擎运行时读取）
KEY_EMERGENCY_STOP = "risk:emergency_stop"
KEY_DAILY_LOSS_LIMIT = "risk:daily_loss_limit"

# ★ 全局风控参数（对齐演示稿 4 卡：延迟红线/名义上限/提现风控/跨所拦截）
RISK_RULES: dict[str, dict] = {
    "delay_red_line_a": {"default": 10, "label": "跟单延迟红线·模式A", "unit": "s", "group": "延迟红线"},
    "delay_red_line_b": {"default": 5, "label": "跟单延迟红线·模式B", "unit": "s", "group": "延迟红线"},
    "notional_limit": {"default": 10000, "label": "单机器人名义上限", "unit": "USDT", "group": "名义上限"},
    "whitelist_exempt": {"default": True, "label": "白名单豁免", "unit": "", "group": "名义上限", "bool": True},
    "min_withdrawal": {"default": 10, "label": "最低提现", "unit": "USDT", "group": "提现风控"},
    "withdrawal_fee": {"default": 1, "label": "手续费", "unit": "USDT", "group": "提现风控"},
    "batch_invite_verify_hours": {"default": 48, "label": "批量邀请核实", "unit": "h", "group": "提现风控"},
    "cross_exchange_block": {"default": True, "label": "跨所拦截", "unit": "", "group": "跨所拦截", "bool": True},
    "api_withdraw_deny": {"default": True, "label": "API 提现权限", "unit": "", "group": "跨所拦截", "bool": True},
}


class EmergencyStopIn(BaseModel):
    enabled: bool


class DailyLossIn(BaseModel):
    limit_usdt: float = Field(gt=0)


class AbuseIn(BaseModel):
    inviter_id: int


class RuleIn(BaseModel):
    key: str
    value: bool | float | int | str


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


@router.get("/rules")
async def get_rules(_admin=Depends(get_current_admin)) -> dict:
    """★ 全局风控参数（Redis 存储，默认值兜底）。"""
    r = _redis()
    out = {}
    for key, meta in RISK_RULES.items():
        raw = r.get(f"risk:rule:{key}")
        if raw is None:
            out[key] = meta["default"]
        elif meta.get("bool"):
            out[key] = raw == "1"
        else:
            try:
                out[key] = float(raw) if "." in raw else int(raw)
            except ValueError:
                out[key] = raw
    return {"rules": out, "meta": RISK_RULES}


@router.post("/rules")
async def set_rule(body: RuleIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ 更新全局风控参数（audit 留痕）。"""
    if body.key not in RISK_RULES:
        raise ValidationError(f"未知参数: {body.key}")
    meta = RISK_RULES[body.key]
    r = _redis()
    before = r.get(f"risk:rule:{body.key}")
    if meta.get("bool"):
        r.set(f"risk:rule:{body.key}", "1" if body.value else "0")
    else:
        r.set(f"risk:rule:{body.key}", str(body.value))
    await AuditService(db).log(
        actor_id=admin["id"], action="risk.rule_update",
        target_type="risk", target_id=body.key,
        before={"value": before}, after={"value": body.value},
    )
    return {"key": body.key, "value": body.value}


@router.get("/high-risk")
async def high_risk_users(db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """★ 高危用户列表：风控冻结 + 1h 批量邀请绑定检测。"""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from api.models.billing import Invite
    from api.models.user import User

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = (await db.execute(select(User).where(User.is_frozen.is_(True)).order_by(User.id.desc()).limit(50))).scalars().all()
    # ★ P1 修复：冻结奖励按 Reward.status='frozen' 真实聚合（此前恒为 0.0 假数据）
    user_ids = [u.id for u in rows]
    frozen_map: dict[int, float] = {}
    if user_ids:
        from api.models.billing import Reward

        frozen_rows = (
            await db.execute(
                select(Reward.owner_id, func.sum(Reward.amount_usdt))
                .where(Reward.owner_id.in_(user_ids), Reward.status == "frozen")
                .group_by(Reward.owner_id)
            )
        ).all()
        frozen_map = {uid: float(total or 0) for uid, total in frozen_rows}
    items = []
    for u in rows:
        bind_count = (
            await db.scalar(
                select(func.count(Invite.id)).where(Invite.inviter_id == u.id, Invite.bound_at >= one_hour_ago)
            )
        ) or 0
        email = u.email or ""
        masked = email[:4] + "***" + (email[email.find("@"):] if "@" in email else "")
        items.append(
            {
                "user_id": u.id,
                "email": masked,
                "trigger": "批量邀请绑定" if bind_count >= 3 else "风控冻结",
                "bind_1h": bind_count,
                "frozen_amount_usdt": round(frozen_map.get(u.id, 0.0), 2),
                "status": "高危冻结",
            }
        )
    return {"items": items}


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
