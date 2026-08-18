# payments 路由（M4 T4.3：创建订单 + 提交 TxHash + 状态查询）
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.core.errors import PaymentError
from api.deps import DbDep, get_current_user
from api.models.billing import PaymentOrder
from api.services.payment.service import PaymentService
from api.services.settings import service as settings_svc

router = APIRouter(prefix="/payments", tags=["payments"])


class CreateOrderIn(BaseModel):
    plan_id: str
    network: Literal["trc20", "bep20", "erc20", "aptos"]


class SubmitTxIn(BaseModel):
    tx_hash: str = ""


@router.post("")
async def create_order(body: CreateOrderIn, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = PaymentService(db)
    order = await svc.create_order(user_id, body.plan_id, body.network)
    # ★ H4 修复：返回该网络 active 平台收款地址（未配置则明确提示，避免支付链路断）
    from sqlalchemy import select

    from api.models.billing import PlatformAddress

    addr = (
        await db.execute(
            select(PlatformAddress.address)
            .where(PlatformAddress.network == body.network, PlatformAddress.status == "active")
            .order_by(PlatformAddress.id.desc())
            .limit(1)
        )
    ).scalars().first()
    ttl_min = int(settings_svc.get_rule("payment_order_ttl_min") or 30)
    return {
        "order_id": order.id,
        "amount_usdt": order.amount_usdt,
        "network": order.network,
        "status": order.status,
        "required_confirmations": order.required_confirmations,
        "platform_address": addr or "",
        "note": "" if addr else f"{body.network} 网络暂未开放收款，请联系客服",
        "ttl_seconds": ttl_min * 60,
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


@router.get("/orders")
async def list_orders(db: DbDep = None, user_id: int = Depends(get_current_user), limit: int = 20) -> dict:
    """我的支付订单历史（订阅页「查看记录」）。limit 默认 20，倒序。"""
    from sqlalchemy import select

    rows = (
        await db.execute(
            select(PaymentOrder)
            .where(PaymentOrder.user_id == user_id)
            .order_by(PaymentOrder.id.desc())
            .limit(min(max(limit, 1), 100))
        )
    ).scalars().all()
    return {
        "orders": [
            {
                "order_id": o.id,
                "plan_id": o.plan_id,
                "amount_usdt": o.amount_usdt,
                "network": o.network,
                "status": o.status,
                "confirmations": o.confirmations,
                "required": o.required_confirmations,
                "tx_hash": o.tx_hash or "",
                "created_at": o.created_at.isoformat() if o.created_at else "",
            }
            for o in rows
        ]
    }


@router.get("/{order_id}")
async def get_order(order_id: int, db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
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
