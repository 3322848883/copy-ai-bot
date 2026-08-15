# apikeys 路由（M1 T1.5/T1.6）
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Request

from api.core.errors import ApiKeyError
from api.deps import DbDep, get_current_user
from api.services.apikeyvault.service import ApiKeyService, ApiKeyVaultService
from api.services.audit.service import AuditService

router = APIRouter(prefix="/apikeys", tags=["apikeys"])


class BindApiKeyIn(BaseModel):
    exchange: str
    api_key: str = Field(min_length=8)
    api_secret: str = Field(min_length=8)


@router.post("", status_code=201)
async def bind_apikey(body: BindApiKeyIn, request: Request, db: DbDep, user_id: int = Depends(get_current_user)) -> dict:
    svc = ApiKeyService(db, ApiKeyVaultService(), AuditService(db))
    try:
        record = await svc.bind(
            user_id=user_id,
            exchange=body.exchange,
            api_key=body.api_key,
            api_secret=body.api_secret,
            ip=request.client.host if request.client else None,
        )
    except ApiKeyError:
        raise
    return {"message": "API 绑定成功", "exchange": record.exchange, "id": record.id}


@router.get("")
async def list_apikeys(db: DbDep, user_id: int = Depends(get_current_user)) -> dict:
    """已绑定交易所 API（仅返回交易所与 id，不泄露密钥）。"""
    from sqlalchemy import select

    from api.models.user import ApiKey

    rows = (
        await db.execute(select(ApiKey).where(ApiKey.user_id == user_id))
    ).scalars().all()
    return {"items": [{"id": k.id, "exchange": k.exchange} for k in rows]}


@router.delete("/{exchange}")
async def unbind_apikey(exchange: str, request: Request, db: DbDep, user_id: int = Depends(get_current_user)) -> dict:
    svc = ApiKeyService(db, ApiKeyVaultService(), AuditService(db))
    await svc.unbind(user_id, exchange, ip=request.client.host if request.client else None)
    return {"message": f"已解绑 {exchange} API"}
