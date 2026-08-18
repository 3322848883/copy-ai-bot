# notification 模块（M1 T1.3：站内消息 + WS 推送）
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.audit import Notification


def _to_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


class NotificationService:
    """站内消息：入库 + WS 实时推送（离线用户下次连接拉取）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def push(self, user_id: int, type: str, title: str, body: str | None = None) -> Notification:
        """创建站内消息（入库 + notification.new 实时推送）。"""
        notif = Notification(user_id=user_id, type=type, title=title, body=body, is_read=False)
        self.db.add(notif)
        await self.db.commit()
        await self.db.refresh(notif)
        try:
            from api.ws.hub import hub

            await hub.push(user_id, "notification.new", _to_dict(notif))
        except Exception:  # noqa: BLE001 WS 推送失败不影响入库
            pass
        return notif

    async def list(self, user_id: int, unread_only: bool = False, limit: int = 30, offset: int = 0) -> list[dict]:
        """站内消息列表（按 id 倒序）。"""
        stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        stmt = stmt.order_by(Notification.id.desc()).limit(limit).offset(offset)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_to_dict(n) for n in rows]

    async def unread_count(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.is_read.is_(False)
            )
        )
        return int(result.scalar() or 0)

    async def mark_read(self, user_id: int, notification_id: int) -> bool:
        """标记单条已读（仅本人消息）。"""
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        )
        await self.db.commit()
        return bool(result.rowcount)

    async def mark_all_read(self, user_id: int) -> int:
        """全部已读，返回影响行数。"""
        result = await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
        await self.db.commit()
        return int(result.rowcount or 0)
