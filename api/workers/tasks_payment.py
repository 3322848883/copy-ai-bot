# 支付轮询 1/5/10/20 min（★ G09，M4 T4.3）
from __future__ import annotations

import asyncio
import logging

from api.workers.celery_app import celery_app

logger = logging.getLogger("signal-saas.workers.payment")


@celery_app.task(name="payment.poll_sweep")
def poll_payment_sweep() -> str:
    """扫全部 verifying/polling 订单逐个轮询（Celery Beat 每 2 分钟）。"""
    try:
        asyncio.get_running_loop()
        raise RuntimeError("存在运行中的 loop，请 await poll_payment_sweep_async()")
    except RuntimeError:
        return asyncio.run(poll_payment_sweep_async())


async def poll_payment_sweep_async() -> str:
    """async 核心：扫描轮询态订单。"""
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.billing import PaymentOrder
    from api.services.payment.service import PaymentService

    factory = get_session_factory()
    async with factory() as db:
        rows = (
            await db.execute(
                select(PaymentOrder).where(
                    PaymentOrder.status.in_(["verifying", "polling"])
                )
            )
        ).scalars().all()
        svc = PaymentService(db)
        results = []
        for order in rows:
            updated = await svc.poll_order(order.id)
            results.append(f"{order.id}:{updated.status}")
        return " | ".join(results) or "no polling orders"


@celery_app.task(name="payment.poll")
def poll_payment(order_id: int) -> str:
    """轮询链上确认数；超限转 manual/timeout。"""
    from api.db.session import get_session_factory
    from api.services.payment.service import PaymentService

    async def _run() -> str:
        factory = get_session_factory()
        async with factory() as db:
            svc = PaymentService(db)
            order = await svc.poll_order(order_id)
            return f"order {order.id}: {order.status} conf={order.confirmations} attempts={order.poll_attempts}"

    try:
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        logger.exception("poll order %s failed: %s", order_id, exc)
        raise
