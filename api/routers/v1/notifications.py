# notifications 路由（站内消息：列表 / 未读数 / 已读 / 全部已读）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import DbDep, get_current_user
from api.services.notification.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: DbDep = None,
    user_id: int = Depends(get_current_user),
) -> dict:
    svc = NotificationService(db)
    items = await svc.list(user_id, unread_only=unread_only, limit=limit, offset=offset)
    unread = await svc.unread_count(user_id)
    return {"items": items, "unread_count": unread}


@router.get("/unread-count")
async def unread_count(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = NotificationService(db)
    return {"unread_count": await svc.unread_count(user_id)}


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: DbDep = None,
    user_id: int = Depends(get_current_user),
) -> dict:
    svc = NotificationService(db)
    ok = await svc.mark_read(user_id, notification_id)
    return {"message": "已标记已读" if ok else "消息不存在或已是已读", "updated": ok}


@router.post("/read-all")
async def mark_all_read(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = NotificationService(db)
    count = await svc.mark_all_read(user_id)
    return {"message": f"已将 {count} 条消息标记为已读", "updated": count}
