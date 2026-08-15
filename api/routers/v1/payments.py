# payments 路由（M4 T4.3：创建订单 + 提交 TxHash + 状态查询）
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.core.errors import PaymentError
from api.deps import DbDep, get_current_user
from api.models.billing import PaymentOrder
from api.services.payment.service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


class CreateOrderIn(BaseModel):
    plan_id: str
    network: Literal["trc20", "bep20", "erc20"]


class SubmitTxIn(BaseModel):
    tx_hash: str = ""


@router.post("")
async def create_order(body: CreateOrderIn, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = PaymentService(db)
    order = await svc.create_order(user_id, body.plan_id, body.network)
    return {
        "order_id": order.id,
        "amount_usdt": order.amount_usdt,
        "network": order.network,
        "status": order.status,
        "required_confirmations": order.required_confirmations,
    }


@router.post("/{order_id}/tx")
async def submit_tx(order_id: int, body: SubmitTxIn, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = PaymentService(db)
    order = await svc.submit_tx(order_id, user_id, body.tx_hash)
    return {
        "order_id": order.id,
        "status": order.status,
        "confirmations": order.confirmations,
        "required": order.required_confirmations,
    }


@router.get("/{order_id}")
async def get_order(order_id: int, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = PaymentService(db)
    order = await db.get(PaymentOrder, order_id)
    if order is None or order.user_id != user_id:
        raise PaymentError("订单不存在")
    return {
        "order_id": order.id,
        "plan_id": order.plan_id,
        "amount_usdt": order.amount_usdt,
        "network": order.network,
        "status": order.status,
        "confirmations": order.confirmations,
        "required": order.required_confirmations,
        "poll_attempts": order.poll_attempts,
    }
