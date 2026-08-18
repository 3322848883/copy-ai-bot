"""临时：prod 支付轮询器。周期性扫描 verifying/polling 订单并调用 PaymentService.poll_order（真实 RPC），
实现真实链上到账自动确认。独立运行，不依赖 Celery。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("APP_ENV", "prod")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://signal:paytest-prod-pg-2026@localhost:5433/signal_saas",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6381/0")
os.environ.setdefault("JWT_SECRET", "prodtest-jwt-secret-0123456789abcdef-0123456789")

INTERVAL = 12  # 秒


async def main() -> None:
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.billing import PaymentOrder
    from api.services.payment.service import PaymentService

    while True:
        try:
            factory = get_session_factory()
            async with factory() as db:
                rows = (
                    (await db.execute(select(PaymentOrder).where(PaymentOrder.status.in_(["verifying", "polling"]))))
                    .scalars()
                    .all()
                )
                for o in rows:
                    try:
                        svc = PaymentService(db)
                        await svc.poll_order(o.id)
                        print(f"polled order#{o.id} network={o.network} attempts={o.poll_attempts}")
                    except Exception as e:  # noqa: BLE001
                        print(f"poll error order#{o.id}: {e}")
                if rows:
                    await db.commit()
        except Exception as e:  # noqa: BLE001
            print(f"scan error: {e}")
        await asyncio.sleep(INTERVAL)


asyncio.run(main())