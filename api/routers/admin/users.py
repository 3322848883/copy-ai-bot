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


@router.get("")
async def list_users(
    q: str = Query("", description="邮箱模糊搜索"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from sqlalchemy import func, select

    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(User.email.ilike(like))
        count_stmt = count_stmt.where(User.email.ilike(like))
    total = await db.scalar(count_stmt) or 0
    rows = (await db.execute(stmt.order_by(User.id.desc()).offset((page - 1) * size).limit(size))).scalars().all()
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
                "created_at": u.created_at.isoformat() if hasattr(u, "created_at") else None,
            }
            for u in rows
        ],
    }


@router.get("/{user_id}")
async def user_detail(user_id: int, db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    u = await db.get(User, user_id)
    if u is None:
        raise NotFoundError("用户不存在")
    return {
        "id": u.id,
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "is_frozen": u.is_frozen,
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
