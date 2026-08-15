# 监控路由（M6 T6.5：健康检查 + Prometheus /metrics）
from __future__ import annotations

from fastapi import APIRouter, Request

from api.core.config import get_settings

router = APIRouter(tags=["monitoring"])


@router.get("/healthz/detailed")
async def health_detailed() -> dict:
    """详细健康检查：db / redis 连通性。"""
    settings = get_settings()
    checks: dict[str, str] = {}
    try:
        from sqlalchemy import text

        from api.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            await db.execute(text("SELECT 1"))
        checks["postgres"] = "up"
    except Exception:  # noqa: BLE001
        checks["postgres"] = "down"
    try:
        import redis

        r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        checks["redis"] = "up"
    except Exception:  # noqa: BLE001
        checks["redis"] = "down"
    overall = "ok" if set(checks.values()) == {"up"} else "degraded"
    return {"status": overall, "checks": checks}


@router.get("/metrics")
async def metrics(request: Request) -> str:
    """Prometheus 文本格式：进程级 + 业务关键指标（6 核心指标 + 派生 gauge）。"""
    from sqlalchemy import func, select

    from api.db.session import get_session_factory
    from api.models.audit import AuditEvent
    from api.models.billing import PaymentOrder, Withdrawal
    from api.models.bot import CopyOrder
    from api.models.user import User
    from api.core import metrics as M

    try:
        factory = get_session_factory()
        async with factory() as db:
            M.app_users_total.set(await db.scalar(select(func.count(User.id))) or 0)
            M.app_audit_events_total.set(await db.scalar(select(func.count(AuditEvent.id))) or 0)
            M.app_copy_orders_filled_total.inc(await db.scalar(select(func.count(CopyOrder.id)).where(CopyOrder.status == "filled")) or 0)
            M.app_copy_orders_failed_total.inc(await db.scalar(select(func.count(CopyOrder.id)).where(CopyOrder.status == "failed")) or 0)
            M.app_payments_confirmed_total.inc(await db.scalar(select(func.count(PaymentOrder.id)).where(PaymentOrder.status == "confirmed")) or 0)
            M.withdrawal_pending_total.set(
                await db.scalar(
                    select(func.count(Withdrawal.id)).where(Withdrawal.status.in_(["pending_review", "approved", "processing"]))
                )
                or 0
            )
    except Exception:  # noqa: BLE001 DB 不可用仅记录
        pass

    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    from fastapi.responses import Response

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
