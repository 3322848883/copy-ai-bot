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
