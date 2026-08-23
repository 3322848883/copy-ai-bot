# admin/subscriptions 路由（★ 订阅管理：列表 / 手动开通 / 编辑到期 / 撤销）
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.core.errors import NotFoundError, ValidationError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.billing import Subscription
from api.models.user import User
from api.services.audit.service import AuditService
from api.services.billing.service import BillingService

router = APIRouter(prefix="/subscriptions", tags=["admin-subscriptions"])


class ManualOpenIn(BaseModel):
    user_id: int = Field(gt=0)
    plan_id: str = Field(min_length=1, max_length=64)
    duration_days: int | None = Field(default=None, gt=0, le=3650)


class SubscriptionPatchIn(BaseModel):
    status: str | None = None  # active / expired
    expires_at: str | None = None  # ISO 时间（延长/修改到期时间）


def _sub_dict(sub: Subscription, email: str | None = None) -> dict:
    return {
        "id": sub.id,
        "user_id": sub.user_id,
        "email": email,
        "plan_id": sub.plan_id,
        "status": sub.status,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "payment_order_id": sub.payment_order_id,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


@router.get("")
async def list_subscriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(""),
    keyword: str = Query(""),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    """订阅列表（分页 + 状态筛选 + 用户邮箱搜索）。"""
    from sqlalchemy import func, select

    q = select(Subscription, User.email).join(User, User.id == Subscription.user_id)
    if status:
        q = q.where(Subscription.status == status)
    if keyword:
        q = q.where(User.email.ilike(f"%{keyword}%"))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (
        (await db.execute(q.order_by(Subscription.id.desc()).offset((page - 1) * page_size).limit(page_size)))
        .all()
    )
    items = [_sub_dict(sub, email) for sub, email in rows]
    return {"items": items, "total": total or 0, "page": page, "page_size": page_size}


@router.post("")
async def manual_open(body: ManualOpenIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ 管理员手动开通订阅（绕过支付流程，方便用户管理）。"""
    user = await db.get(User, body.user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    billing = BillingService(db)
    sub = await billing.activate_subscription_manual(
        user_id=body.user_id, plan_id=body.plan_id, duration_days=body.duration_days
    )
    await AuditService(db).log(
        actor_id=admin["id"], action="subscription.manual_open",
        target_type="user", target_id=str(body.user_id),
        after={"plan_id": body.plan_id, "duration_days": body.duration_days,
               "expires_at": sub.expires_at.isoformat()},
    )
    return _sub_dict(sub, user.email)


@router.patch("/{sub_id}")
async def patch_subscription(sub_id: int, body: SubscriptionPatchIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """修改订阅：延长到期时间 / 改状态（撤销）。"""
    sub = await db.get(Subscription, sub_id)
    if sub is None:
        raise NotFoundError("订阅不存在")
    before = {"status": sub.status, "expires_at": sub.expires_at.isoformat() if sub.expires_at else None}
    if body.status is not None:
        if body.status not in ("active", "expired"):
            raise ValidationError("status 必须为 active / expired")
        sub.status = body.status
    if body.expires_at is not None:
        try:
            new_exp = datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise ValidationError("expires_at 格式错误，需 ISO 时间")
        if new_exp.tzinfo is None:
            new_exp = new_exp.replace(tzinfo=timezone.utc)
        sub.expires_at = new_exp
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="subscription.patch",
        target_type="subscription", target_id=str(sub_id),
        before=before,
        after={"status": sub.status, "expires_at": sub.expires_at.isoformat() if sub.expires_at else None},
    )
    return _sub_dict(sub)


@router.delete("/{sub_id}")
async def delete_subscription(sub_id: int, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """撤销订阅（删除记录）。"""
    sub = await db.get(Subscription, sub_id)
    if sub is None:
        raise NotFoundError("订阅不存在")
    await db.delete(sub)
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="subscription.delete",
        target_type="subscription", target_id=str(sub_id),
        before={"user_id": sub.user_id, "plan_id": sub.plan_id, "status": sub.status},
    )
    return {"ok": True}
