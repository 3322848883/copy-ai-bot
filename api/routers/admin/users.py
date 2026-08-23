# admin/users 路由（M5 T5.2：用户列表 + 冻结/解冻；写操作强制 audit-log）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.core.errors import NotFoundError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.user import User
from api.services.audit.service import AuditService

router = APIRouter(prefix="/users", tags=["admin-users"])


class FreezeIn(BaseModel):
    frozen: bool


class NoteIn(BaseModel):
    note: str | None = None


@router.get("")
async def list_users(
    q: str = Query("", description="邮箱模糊搜索"),
    status: str = Query("", description="normal=正常 / frozen=已冻结（服务端筛选，保证跨页完整）"),
    subscription_status: str = Query("", description="active=已订阅 / expired=已过期 / none=未订阅"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from datetime import datetime, timezone

    from sqlalchemy import exists, func, select

    from api.core.errors import ValidationError
    from api.models.billing import Subscription
    from api.services.settings.service import get_plans

    if status not in ("", "normal", "frozen"):
        raise ValidationError("status 仅支持 normal/frozen")
    if subscription_status not in ("", "active", "expired", "none"):
        raise ValidationError("subscription_status 仅支持 active/expired/none")
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(User.email.ilike(like))
        count_stmt = count_stmt.where(User.email.ilike(like))
    # ★ P1：正常/冻结筛选走服务端——此前前端仅在首屏 50 条内过滤，第 2 页起记录被漏掉
    if status == "frozen":
        stmt = stmt.where(User.is_frozen.is_(True))
        count_stmt = count_stmt.where(User.is_frozen.is_(True))
    elif status == "normal":
        stmt = stmt.where(User.is_frozen.is_(False), User.is_active.is_(True))
        count_stmt = count_stmt.where(User.is_frozen.is_(False), User.is_active.is_(True))
    # ★ 订阅状态筛选（服务端 EXISTS 判断，跨页完整）
    now = datetime.now(timezone.utc)
    if subscription_status == "active":
        _has_active = exists().where(
            Subscription.user_id == User.id,
            Subscription.status == "active",
            Subscription.expires_at > now,
        )
        stmt = stmt.where(_has_active)
        count_stmt = count_stmt.where(_has_active)
    elif subscription_status == "expired":
        _has_sub = exists().where(Subscription.user_id == User.id)
        _has_active = exists().where(
            Subscription.user_id == User.id,
            Subscription.status == "active",
            Subscription.expires_at > now,
        )
        stmt = stmt.where(_has_sub, ~_has_active)
        count_stmt = count_stmt.where(_has_sub, ~_has_active)
    elif subscription_status == "none":
        _has_sub = exists().where(Subscription.user_id == User.id)
        stmt = stmt.where(~_has_sub)
        count_stmt = count_stmt.where(~_has_sub)
    total = await db.scalar(count_stmt) or 0
    rows = (await db.execute(stmt.order_by(User.id.desc()).offset((page - 1) * size).limit(size))).scalars().all()
    # ★ 批量获取订阅状态（每用户最新一条 active 订阅，含过期判断）
    sub_map: dict[int, dict] = {}
    if rows:
        plan_names = {p.get("plan_id"): p.get("name") or p.get("plan_id") for p in get_plans()}
        sub_rows = (
            await db.execute(
                select(Subscription.user_id, Subscription.plan_id, Subscription.expires_at)
                .where(
                    Subscription.user_id.in_([u.id for u in rows]),
                    Subscription.status == "active",
                )
                .order_by(Subscription.expires_at.desc())
            )
        ).all()
        for uid, pid, exp in sub_rows:
            if uid in sub_map:
                continue
            e = exp
            if e.tzinfo is None:
                e = e.replace(tzinfo=timezone.utc)
            sub_map[uid] = {
                "plan_id": pid,
                "plan_name": plan_names.get(pid, pid),
                "status": "active" if e > now else "expired",
                "expires_at": exp.isoformat() if exp else None,
            }
    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "is_frozen": u.is_frozen,
                "risk_disclosure_accepted": u.risk_disclosure_accepted,
                "subscription": sub_map.get(u.id),
                "created_at": u.created_at.isoformat() if hasattr(u, "created_at") else None,
            }
            for u in rows
        ],
    }


@router.get("/{user_id}")
async def user_detail(user_id: int, db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """用户详情（★ 财务概览 + 跟单概览 + 所选交易所）。"""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from api.models.bot import CopyBot, CopyOrder
    from api.models.user import Identity
    from api.services.ledger.service import LedgerService

    u = await db.get(User, user_id)
    if u is None:
        raise NotFoundError("用户不存在")

    identity = (
        await db.execute(select(Identity).where(Identity.user_id == user_id))
    ).scalars().first()
    bal = await LedgerService(db).balance(user_id)

    # 跟单概览：运行机器人 / 今日成交 / 本周订单
    bots = (await db.execute(select(CopyBot).where(CopyBot.user_id == user_id))).scalars().all()
    running_bots = sum(1 for b in bots if b.status == "active")
    bot_ids = [b.id for b in bots]
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    today_orders = 0
    week_orders_count = 0
    if bot_ids:
        today_orders = (
            await db.scalar(
                select(func.count(CopyOrder.id)).where(
                    CopyOrder.bot_id.in_(bot_ids),
                    CopyOrder.status == "filled",
                    CopyOrder.executed_at >= today_start,
                )
            )
        ) or 0
        week_orders_count = (
            await db.scalar(
                select(func.count(CopyOrder.id)).where(
                    CopyOrder.bot_id.in_(bot_ids),
                    CopyOrder.executed_at >= week_start,
                )
            )
        ) or 0

    return {
        "id": u.id,
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "is_frozen": u.is_frozen,
        "risk_disclosure_accepted": u.risk_disclosure_accepted,
        "exchange": identity.exchange if identity else None,
        "identity_type": identity.identity_type if identity else None,
        "admin_note": u.admin_note,
        "financial": bal,
        "copy": {
            "running_bots": running_bots,
            "today_orders": today_orders,
            "week_orders_count": week_orders_count,
        },
    }


@router.patch("/{user_id}/freeze")
async def freeze_user(user_id: int, body: FreezeIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """冻结/解冻用户（★ 冻结后禁止登录、下单、提现）。"""
    u = await db.get(User, user_id)
    if u is None:
        raise NotFoundError("用户不存在")
    before = u.is_frozen
    u.is_frozen = body.frozen
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="user.freeze" if body.frozen else "user.unfreeze",
        target_type="user", target_id=str(user_id),
        before={"is_frozen": before}, after={"is_frozen": u.is_frozen},
    )
    return {"id": user_id, "is_frozen": u.is_frozen}


@router.patch("/{user_id}/note")
async def update_user_note(user_id: int, body: NoteIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ 用户管理「备注」：保存/清空管理员备注（audit 留痕）。"""
    u = await db.get(User, user_id)
    if u is None:
        raise NotFoundError("用户不存在")
    before = u.admin_note
    u.admin_note = (body.note or "").strip() or None
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="user.note_update",
        target_type="user", target_id=str(user_id),
        before={"admin_note": before}, after={"admin_note": u.admin_note},
    )
    return {"id": user_id, "admin_note": u.admin_note}
