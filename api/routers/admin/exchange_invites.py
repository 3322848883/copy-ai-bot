# admin/exchange_invites 路由（M5 T5.3：★ G27 交易所邀请码 CRUD + 绑定计数）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.core.errors import NotFoundError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.exchange import ExchangeInviteCode
from api.services.audit.service import AuditService

router = APIRouter(prefix="/exchange-invites", tags=["admin-exchange-invites"])


class InviteCodeIn(BaseModel):
    exchange: str
    code: str = Field(min_length=4, max_length=32)
    max_binds: int | None = Field(default=None, ge=1)
    remark: str | None = Field(default=None, max_length=128)


class StatusIn(BaseModel):
    status: str  # active / inactive


@router.get("")
async def list_codes(
    exchange: str = Query(""),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from sqlalchemy import select

    stmt = select(ExchangeInviteCode).order_by(ExchangeInviteCode.id.desc())
    if exchange:
        stmt = stmt.where(ExchangeInviteCode.exchange == exchange)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": c.id,
                "exchange": c.exchange,
                "code": c.code,
                "status": c.status,
                "remark": c.remark,
                "bind_count": c.bind_count,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "max_binds": c.max_binds,
            }
            for c in rows
        ]
    }


@router.post("")
async def create_code(body: InviteCodeIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    record = ExchangeInviteCode(
        exchange=body.exchange, code=body.code.upper(),
        max_binds=body.max_binds, remark=body.remark, status="active",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    await AuditService(db).log(
        actor_id=admin["id"], action="exchange_invite.create",
        target_type="exchange_invite", target_id=str(record.id),
        after={"exchange": record.exchange, "code": record.code},
    )
    return {"id": record.id, "exchange": record.exchange, "code": record.code}


@router.patch("/{code_id}/status")
async def update_status(code_id: int, body: StatusIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    record = await db.get(ExchangeInviteCode, code_id)
    if record is None:
        raise NotFoundError("邀请码不存在")
    before = record.status
    record.status = body.status
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="exchange_invite.status",
        target_type="exchange_invite", target_id=str(code_id),
        before={"status": before}, after={"status": record.status},
    )
    return {"id": code_id, "status": record.status}


@router.delete("/{code_id}")
async def delete_code(code_id: int, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    record = await db.get(ExchangeInviteCode, code_id)
    if record is None:
        raise NotFoundError("邀请码不存在")
    await db.delete(record)
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="exchange_invite.delete",
        target_type="exchange_invite", target_id=str(code_id),
        after={"exchange": record.exchange, "code": record.code},
    )
    return {"deleted": True}


# ── ★ 用户绑定复核：绑定交易所邀请码后需管理员批准才免订阅 ──


@router.get("/bindings/list")
async def list_bindings(
    status: str = Query(""),  # pending / approved / rejected，空=全部
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from sqlalchemy import select

    from api.models.user import Identity, User

    stmt = (
        select(Identity, User.email)
        .join(User, User.id == Identity.user_id)
        .where(Identity.exchange_invite_code.is_not(None))
        .order_by(Identity.updated_at.desc())
    )
    if status:
        stmt = stmt.where(Identity.exchange_invite_status == status)
    rows = (await db.execute(stmt)).all()
    return {
        "items": [
            {
                "user_id": ident.user_id,
                "email": email,
                "exchange": ident.exchange,
                "code": ident.exchange_invite_code,
                "status": ident.exchange_invite_status or "pending",
                "updated_at": ident.updated_at.isoformat() if ident.updated_at else None,
            }
            for ident, email in rows
        ]
    }


async def _set_binding_status(db, admin: dict, user_id: int, new_status: str, action: str) -> dict:
    from api.models.user import Identity
    from api.services.notification.service import NotificationService

    identity = await db.get(Identity, user_id)
    if identity is None or not identity.exchange_invite_code:
        raise NotFoundError("该用户未绑定交易所邀请码")
    before = identity.exchange_invite_status
    identity.exchange_invite_status = new_status
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action=action,
        target_type="identity", target_id=str(user_id),
        before={"status": before}, after={"status": new_status, "code": identity.exchange_invite_code},
    )
    if new_status == "approved":
        await NotificationService(db).push(
            user_id, "exchange_invite", "交易所邀请码复核通过",
            "你的交易所邀请码已通过复核，跟单功能免订阅长期有效。",
        )
    else:
        await NotificationService(db).push(
            user_id, "exchange_invite", "交易所邀请码复核未通过",
            "你提交的交易所邀请码未通过复核，可前往个人中心重新绑定。",
        )
    return {"user_id": user_id, "status": new_status}


@router.post("/bindings/{user_id}/approve")
async def approve_binding(user_id: int, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    return await _set_binding_status(db, admin, user_id, "approved", "exchange_invite_binding.approve")


@router.post("/bindings/{user_id}/reject")
async def reject_binding(user_id: int, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    return await _set_binding_status(db, admin, user_id, "rejected", "exchange_invite_binding.reject")
