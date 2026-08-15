# admin/invites 路由（M5：邀请奖励看板 —— KPI + 刷单告警 + 邀请关系列表）
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from api.deps import DbDep, get_current_admin
from api.models.billing import Invite, PaymentOrder, Reward
from api.models.user import Identity, User

router = APIRouter(prefix="/invites", tags=["admin-invites"])

STATUS_LABEL = {
    "verifying": "核实中", "available": "已到账", "withdrawing": "提现中",
    "paid": "已提现", "frozen": "冻结", "canceled": "已取消",
    "paid_failed": "发放失败", "rolled_back": "已回滚",
}


@router.get("/kpi")
async def kpi(db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """KPI：今日触发 / 核实中 / 已到账 / 已取消 / 风控冻结。"""
    from sqlalchemy import func, select

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = (
        await db.execute(
            select(func.count(Reward.id), func.coalesce(func.sum(Reward.amount_usdt), 0.0)).where(
                Reward.created_at >= today_start, Reward.amount_usdt > 0
            )
        )
    ).one()
    verifying = (
        await db.scalar(select(func.count(Reward.id)).where(Reward.status == "verifying"))
    ) or 0
    available = (
        await db.scalar(select(func.count(Reward.id)).where(Reward.status == "available"))
    ) or 0
    canceled = (
        await db.scalar(
            select(func.count(Reward.id)).where(Reward.status.in_(["canceled", "rolled_back"]))
        )
    ) or 0
    frozen = (
        await db.scalar(
            select(func.count(Reward.id)).where(Reward.status.in_(["frozen", "paid_failed"]))
        )
    ) or 0
    return {
        "today_count": today[0],
        "today_amount_usdt": round(today[1], 2),
        "verifying_count": verifying,
        "available_count": available,
        "canceled_count": canceled,
        "frozen_count": frozen,
    }


@router.get("/abuse")
async def abuse(db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """★ G11 刷单告警：1h 内绑定 ≥3 个邀请码的用户（detect_batch_abuse）。"""
    from sqlalchemy import func, select

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = (
        await db.execute(
            select(Invite.inviter_id, func.count(Invite.id), User.email)
            .join(User, User.id == Invite.inviter_id)
            .where(Invite.bound_at >= one_hour_ago)
            .group_by(Invite.inviter_id, User.email)
            .having(func.count(Invite.id) >= 3)
            .order_by(func.count(Invite.id).desc())
        )
    ).all()
    return {
        "items": [
            {"inviter_id": rid, "email": email, "bind_count": n}
            for rid, n, email in rows
        ],
        "threshold": 3,
        "window_hours": 1,
    }


@router.get("")
async def relations(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    """邀请关系列表：邀请人/邀请码/下级/触发金额/奖励/核实状态。"""
    from sqlalchemy import func, select

    # 每笔奖励 + 邀请信息（code 经 invitee 关联 Invite）
    stmt = (
        select(Reward, User, Invite, PaymentOrder)
        .join(User, User.id == Reward.owner_id, isouter=True)
        .join(Invite, Invite.invitee_id == Reward.source_user_id, isouter=True)
        .join(PaymentOrder, PaymentOrder.id == Reward.source_payment_order_id, isouter=True)
        .order_by(Reward.id.desc())
    )
    count_stmt = select(func.count(Reward.id))
    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.execute(stmt.offset((page - 1) * size).limit(size))
    ).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "inviter_email": inv.email if inv else str(r.owner_id),
                "code": iv.code if iv else "",
                "invitee_id": r.source_user_id,
                "trigger_amount_usdt": po.amount_usdt if po else 0,
                "reward_usdt": r.amount_usdt,
                "status": r.status,
                "status_label": STATUS_LABEL.get(r.status, r.status),
                "verifying_ends_at": r.verifying_ends_at.isoformat() if r.verifying_ends_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r, inv, iv, po in rows
        ],
    }