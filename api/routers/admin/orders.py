# admin/orders 路由（M5：跟单订单全平台监控 + 失败归类报表，写操作强制 audit-log）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import DbDep, get_current_admin
from api.models.bot import CopyBot, CopyOrder
from api.models.signal import SourceSignal, Strategy
from api.models.user import User

router = APIRouter(prefix="/orders", tags=["admin-orders"])

ACTION_LABEL = {"open": "开仓", "add": "加仓", "reduce": "减仓", "close": "平仓"}
STATUS_LABEL = {"pending": "待执行", "filled": "已成交", "failed": "已失败", "cancelled": "已取消"}


@router.get("")
async def list_orders(
    action: str = Query(""),
    status: str = Query(""),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    """全平台订单列表，按 动作/状态/交易所 过滤，join 用户与策略。"""
    from sqlalchemy import func, select

    stmt = (
        select(CopyOrder, CopyBot, Strategy, User, SourceSignal)
        .join(CopyBot, CopyBot.id == CopyOrder.bot_id)
        .join(Strategy, Strategy.id == CopyBot.strategy_id, isouter=True)
        .join(User, User.id == CopyBot.user_id, isouter=True)
        .join(SourceSignal, SourceSignal.id == CopyOrder.signal_id, isouter=True)
    )
    count_stmt = select(func.count(CopyOrder.id)).join(CopyBot, CopyBot.id == CopyOrder.bot_id)
    if action:
        stmt = stmt.where(CopyOrder.action == action)
        count_stmt = count_stmt.where(CopyOrder.action == action)
    if status:
        stmt = stmt.where(CopyOrder.status == status)
        count_stmt = count_stmt.where(CopyOrder.status == status)

    total = await db.scalar(count_stmt) or 0
    rows = (await db.execute(stmt.order_by(CopyOrder.id.desc()).offset((page - 1) * size).limit(size))).all()
    return {
        "total": total,
        "items": [
            {
                "id": o.id,
                "bot_id": o.bot_id,
                "user_id": bot.user_id,
                "user_email": u.email if u else str(bot.user_id),
                "strategy_name": s.display_name if s else "未知策略",
                "action": o.action,
                "action_label": ACTION_LABEL.get(o.action, o.action),
                "symbol": sig.symbol if sig else "",
                "side": sig.side if sig else "",
                "leverage": o.leverage,
                "qty": o.qty,
                "required_margin_usdt": o.required_margin_usdt,
                "status": o.status,
                "status_label": STATUS_LABEL.get(o.status, o.status),
                "failure_category": o.failure_category or "",
                "latency_ms": o.latency_ms,
                "executed_at": o.executed_at.isoformat() if o.executed_at else None,
            }
            for o, bot, s, u, sig in rows
        ],
    }


@router.get("/failures")
async def failure_report(db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """失败归类报表：failure_category 枚举分布 + KPI。
    ★ P1 修复：KPI 标签是「今日订单」，此前却统计全量 CopyOrder——日期口径错误，改为
    今日（UTC 0 点起；pending 单 executed_at 为空，一并计入今日口径）。"""
    from datetime import datetime, timezone

    from sqlalchemy import func, or_, select

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_scope = or_(
        CopyOrder.executed_at >= today_start,
        (CopyOrder.executed_at.is_(None)) & (CopyOrder.status == "pending"),
    )

    total = (await db.scalar(select(func.count(CopyOrder.id)).where(today_scope))) or 0
    filled = (
        await db.scalar(select(func.count(CopyOrder.id)).where(today_scope, CopyOrder.status == "filled"))
    ) or 0
    failed = (
        await db.scalar(select(func.count(CopyOrder.id)).where(today_scope, CopyOrder.status == "failed"))
    ) or 0
    risk_blocked = (
        await db.scalar(
            select(func.count(CopyOrder.id)).where(
                today_scope, CopyOrder.status == "failed", CopyOrder.failure_category == "risk"
            )
        )
    ) or 0

    breakdown_rows = (
        await db.execute(
            select(CopyOrder.failure_category, func.count(CopyOrder.id))
            .where(today_scope, CopyOrder.failure_category.is_not(None))
            .group_by(CopyOrder.failure_category)
        )
    ).all()
    breakdown = {cat: n for cat, n in breakdown_rows if cat}

    # 平均延迟（仅今日已成交）
    avg_latency = await db.scalar(
        select(func.avg(CopyOrder.latency_ms)).where(
            today_scope, CopyOrder.status == "filled", CopyOrder.latency_ms.is_not(None)
        )
    )

    return {
        "kpi": {
            "total": total,
            "filled": filled,
            "failed": failed,
            "risk_blocked": risk_blocked,
            "fill_rate": round(filled / total * 100, 1) if total else 0,
            "avg_latency_ms": round(avg_latency, 0) if avg_latency is not None else None,
        },
        "breakdown": breakdown,
    }