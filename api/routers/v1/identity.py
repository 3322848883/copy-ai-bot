# identity 路由（M1 T1.4：选所 / 好友码 / 交易所码 G27）
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends

from api.core.errors import AppError, ExchangeInviteError
from api.deps import DbDep, get_current_user
from api.services.audit.service import AuditService
from api.services.identity.service import IdentityService

router = APIRouter(prefix="/identity", tags=["identity"])


class ChooseExchangeIn(BaseModel):
    exchange: str


class BindInviteIn(BaseModel):
    code: str


class BindExchangeInviteIn(BaseModel):
    exchange: str
    code: str


@router.post("/choose-exchange")
async def choose_exchange(body: ChooseExchangeIn, db: DbDep, user_id: int = Depends(get_current_user)) -> dict:
    svc = IdentityService(db, AuditService(db))
    identity = await svc.choose_exchange(user_id, body.exchange)
    return {"exchange": identity.exchange, "identity_type": identity.identity_type}


@router.post("/bind-invite")
async def bind_invite(body: BindInviteIn, db: DbDep, user_id: int = Depends(get_current_user)) -> dict:
    svc = IdentityService(db, AuditService(db))
    identity = await svc.bind_invite_code(user_id, body.code)
    return {
        "invite_code": identity.invite_code,
        "identity_type": identity.identity_type,
        "sub_account": identity.identity_type == "sub_account",
    }


@router.post("/bind-exchange-invite")
async def bind_exchange_invite(
    body: BindExchangeInviteIn, db: DbDep, user_id: int = Depends(get_current_user)
) -> dict:
    svc = IdentityService(db, AuditService(db))
    ok, message = await svc.verify_and_bind_exchange_invite(user_id, body.exchange, body.code)
    if not ok:
        raise ExchangeInviteError(message)
    return {"message": "交易所邀请码绑定成功", "exchange": body.exchange}
