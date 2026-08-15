# admin/payments 路由（M5 T5.6：支付订单列表 + manual 手动确认/标记失败）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.core.errors import NotFoundError, PaymentError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.billing import PaymentOrder
from api.services.audit.service import AuditService

router = APIRouter(prefix="/payments", tags=["admin-payments"])


class ManualIn(BaseModel):
    status: str  # confirmed / failed


@router.get("")
async def list_orders(
    status: str = Query(""),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from sqlalchemy import func, select

    stmt = select(PaymentOrder)
    count_stmt = select(func.count(PaymentOrder.id))
    if status:
        stmt = stmt.where(PaymentOrder.status == status)
        count_stmt = count_stmt.where(PaymentOrder.status == status)
    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.execute(stmt.order_by(PaymentOrder.id.desc()).offset((page - 1) * size).limit(size))
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": o.id,
                "user_id": o.user_id,
                "plan_id": o.plan_id,
                "amount_usdt": o.amount_usdt,
                "network": o.network,
                "tx_hash": o.tx_hash,
                "status": o.status,
                "confirmations": o.confirmations,
                "required": o.required_confirmations,
                "poll_attempts": o.poll_attempts,
            }
            for o in rows
        ],
    }


@router.post("/{order_id}/manual")
async def manual_set(order_id: int, body: ManualIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """manual/verifying 超限订单：人工确认或标记失败。"""
    from api.services.billing.service import BillingService
    from api.services.payment.service import PaymentService

    order = await db.get(PaymentOrder, order_id)
    if order is None:
        raise NotFoundError("订单不存在")
    if order.status not in ("manual", "verifying", "polling", "timeout"):
        raise PaymentError(f"订单状态 {order.status} 不可人工处理")

    before = order.status
    if body.status == "confirmed":
        order.status = "confirmed"
        await db.commit()
        billing = BillingService(db)
        await billing.activate_subscription(order.user_id, order.plan_id, order.id)
        svc = PaymentService(db)
        await svc._trigger_rewards(order)
    else:
        order.status = "failed"
        await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action=f"payment.manual_{body.status}",
        target_type="payment", target_id=str(order_id),
        before={"status": before}, after={"status": order.status},
    )
    return {"id": order_id, "status": order.status}
