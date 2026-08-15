# admin/audit 路由（M5 T5.7：审计日志查询 + 详情）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.core.errors import NotFoundError
from api.deps import DbDep, get_current_admin
from api.models.audit import AuditEvent

router = APIRouter(prefix="/audit", tags=["admin-audit"])


@router.get("")
async def list_audit(
    action: str = Query(""),
    actor_id: int | None = Query(None),
    target_type: str = Query(""),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from sqlalchemy import func, select

    stmt = select(AuditEvent)
    count_stmt = select(func.count(AuditEvent.id))
    if action:
        stmt = stmt.where(AuditEvent.action.ilike(f"%{action}%"))
        count_stmt = count_stmt.where(AuditEvent.action.ilike(f"%{action}%"))
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
        count_stmt = count_stmt.where(AuditEvent.actor_id == actor_id)
    if target_type:
        stmt = stmt.where(AuditEvent.target_type == target_type)
        count_stmt = count_stmt.where(AuditEvent.target_type == target_type)
    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.execute(stmt.order_by(AuditEvent.id.desc()).offset((page - 1) * size).limit(size))
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": e.id,
                "actor_id": e.actor_id,
                "action": e.action,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "before": e.before,
                "after": e.after,
                "reason": e.reason,
                "ip": e.ip,
                "created_at": e.created_at.isoformat(),
            }
            for e in rows
        ],
    }


@router.get("/{event_id}")
async def audit_detail(event_id: int, db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    e = await db.get(AuditEvent, event_id)
    if e is None:
        raise NotFoundError("审计记录不存在")
    return {
        "id": e.id,
        "actor_id": e.actor_id,
        "action": e.action,
        "target_type": e.target_type,
        "target_id": e.target_id,
        "before": e.before,
        "after": e.after,
        "reason": e.reason,
        "ip": e.ip,
        "created_at": e.created_at.isoformat(),
    }
