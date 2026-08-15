# 监控路由（M6 T6.5：健康检查 + Prometheus /metrics）
from __future__ import annotations

import time

from fastapi import APIRouter, Request

from api.core.config import get_settings

router = APIRouter(tags=["monitoring"])

# 简易内存计数器（重启清零；生产接 Prometheus 客户端）
_COUNTERS = {"requests_total": 0}


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
    """Prometheus 文本格式：进程级 + 业务关键指标。"""
    from sqlalchemy import func, select

    from api.db.session import get_session_factory
    from api.models.audit import AuditEvent
    from api.models.billing import PaymentOrder
    from api.models.bot import CopyOrder
    from api.models.user import User

    _COUNTERS["requests_total"] += 1
    lines = [
        "# HELP app_requests_total 累计 HTTP 请求（内存计数）",
        "# TYPE app_requests_total counter",
        f"app_requests_total {_COUNTERS['requests_total']}",
        "# HELP app_up 服务存活",
        "# TYPE app_up gauge",
        "app_up 1",
    ]
    try:
        factory = get_session_factory()
        async with factory() as db:
            users = await db.scalar(select(func.count(User.id))) or 0
            orders_filled = await db.scalar(select(func.count(CopyOrder.id)).where(CopyOrder.status == "filled")) or 0
            orders_failed = await db.scalar(select(func.count(CopyOrder.id)).where(CopyOrder.status == "failed")) or 0
            payments_confirmed = await db.scalar(select(func.count(PaymentOrder.id)).where(PaymentOrder.status == "confirmed")) or 0
            audit_total = await db.scalar(select(func.count(AuditEvent.id))) or 0
        lines += [
            "# HELP app_users_total 注册用户数",
            "# TYPE app_users_total gauge",
            f"app_users_total {users}",
            "# HELP app_copy_orders_filled_total 跟单成功订单数",
            "# TYPE app_copy_orders_filled_total gauge",
            f"app_copy_orders_filled_total {orders_filled}",
            "# HELP app_copy_orders_failed_total 跟单失败订单数",
            "# TYPE app_copy_orders_failed_total gauge",
            f"app_copy_orders_failed_total {orders_failed}",
            "# HELP app_payments_confirmed_total 已确认支付订单数",
            "# TYPE app_payments_confirmed_total gauge",
            f"app_payments_confirmed_total {payments_confirmed}",
            "# HELP app_audit_events_total 审计事件数",
            "# TYPE app_audit_events_total gauge",
            f"app_audit_events_total {audit_total}",
        ]
    except Exception:  # noqa: BLE001
        lines.append("# db_unavailable 1")
    return "\n".join(lines) + "\n"
