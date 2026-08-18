# withdrawals 路由（M4 T4.6：提现申请 + 列表 + 状态查询）
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import DbDep, get_current_user
from api.services.withdrawal.service import WithdrawalService

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


class WithdrawIn(BaseModel):
    network: Literal["trc20", "bep20", "erc20", "aptos"]
    address: str = Field(min_length=3, max_length=128)
    amount_usdt: float = Field(gt=0)


@router.post("")
async def request_withdrawal(body: WithdrawIn, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = WithdrawalService(db)
    wd = await svc.request(user_id, body.network, body.address, body.amount_usdt)
    return {
        "id": wd.id,
        "amount_usdt": wd.amount_usdt,
        "fee_usdt": wd.fee_usdt,
        "status": wd.status,
    }


@router.get("")
async def list_withdrawals(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    from sqlalchemy import select

    from api.models.billing import Withdrawal

    rows = (
        await db.execute(
            select(Withdrawal).where(Withdrawal.user_id == user_id).order_by(Withdrawal.id.desc()).limit(50)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": w.id,
                "amount_usdt": w.amount_usdt,
                "fee_usdt": w.fee_usdt,
                "network": w.network,
                "address": w.address,
                "status": w.status,
                "tx_hash": w.tx_hash,
                "reject_reason": w.reject_reason,
                "created_at": w.created_at.isoformat() if hasattr(w, "created_at") else None,
            }
            for w in rows
        ]
    }


@router.get("/{withdrawal_id}")
async def get_withdrawal(withdrawal_id: int, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    from api.core.errors import NotFoundError

    from api.models.billing import Withdrawal

    wd = await db.get(Withdrawal, withdrawal_id)
    if wd is None or wd.user_id != user_id:
        raise NotFoundError("提现单不存在")
    return {
        "id": wd.id,
        "amount_usdt": wd.amount_usdt,
        "fee_usdt": wd.fee_usdt,
        "network": wd.network,
        "address": wd.address,
        "status": wd.status,
        "tx_hash": wd.tx_hash,
        "reject_reason": wd.reject_reason,
    }
