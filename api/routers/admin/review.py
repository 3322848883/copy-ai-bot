# admin/review 路由（M5：主号下级审核 —— 平台池码命中但所选所不一致的异常申请，人工复核；写操作强制 audit-log）
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.core.errors import NotFoundError, ValidationError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.exchange import PlatformPool
from api.models.user import Identity, User
from api.services.audit.service import AuditService

router = APIRouter(prefix="/review", tags=["admin-review"])


class ReviewIn(BaseModel):
    remark: str | None = None


async def _pool_of_code(db, code: str) -> PlatformPool | None:
    from sqlalchemy import select

    if not code:
        return None
    return (
        await db.execute(
            select(PlatformPool).where(PlatformPool.invite_code == code.upper())
        )
    ).scalars().first()


@router.get("/pending")
async def pending(
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    """待审核申请：已绑定平台池码但 identity_type 仍为 normal（所选所 ≠ 池码所，需人工确认）。"""
    from sqlalchemy import select

    rows = (
        await db.execute(
            select(Identity, User)
            .join(User, User.id == Identity.user_id)
            .where(Identity.invite_code.is_not(None), Identity.identity_type == "normal")
            .order_by(Identity.user_id.asc())
        )
    ).all()
    items = []
    for ident, user in rows:
        pool = await _pool_of_code(db, ident.invite_code)
        if pool is None:
            continue
        items.append(
            {
                "user_id": ident.user_id,
                "email": user.email,
                "invite_code": ident.invite_code,
                "selected_exchange": ident.exchange or "",
                "pool_exchange": pool.exchange,
                "pool_label": pool.label or "",
                "matched": (ident.exchange or "").lower() == pool.exchange.lower(),
            }
        )
    return {"items": items}


@router.get("/done")
async def processed(
    limit: int = 50,
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    """已处理记录：从审计日志回溯 review.approve / review.reject。"""
    from sqlalchemy import select

    from api.models.audit import AuditEvent

    events = (
        await db.execute(
            select(AuditEvent)
            .where(AuditEvent.action.in_(["review.approve", "review.reject"]))
            .order_by(AuditEvent.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": e.id,
                "action": e.action,
                "target_id": e.target_id,
                "actor_id": e.actor_id,
                "reason": e.reason,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    }


@router.post("/{user_id}/approve")
async def approve(user_id: int, body: ReviewIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    ident = await db.get(Identity, user_id)
    if ident is None:
        raise NotFoundError("用户身份不存在")
    ident.identity_type = "sub_account"
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="review.approve",
        target_type="identity", target_id=str(user_id),
        before={"identity_type": "normal"}, after={"identity_type": "sub_account"},
        reason=body.remark or "人工复核通过，标记主号下级（免订阅）",
    )
    return {"user_id": user_id, "identity_type": "sub_account"}


@router.post("/{user_id}/reject")
async def reject(user_id: int, body: ReviewIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    ident = await db.get(Identity, user_id)
    if ident is None:
        raise NotFoundError("用户身份不存在")
    if ident.identity_type == "sub_account":
        raise ValidationError("该用户已是主号下级，无需驳回")
    ident.identity_type = "normal"
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="review.reject",
        target_type="identity", target_id=str(user_id),
        before={"identity_type": ident.identity_type or "normal"}, after={"identity_type": "normal"},
        reason=body.remark or "所选所与池码所不匹配，保留普通用户",
    )
    return {"user_id": user_id, "identity_type": "normal"}