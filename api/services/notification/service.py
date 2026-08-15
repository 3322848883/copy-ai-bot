# notification 模块（M1 T1.3：站内消息 + WS 推送）
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.audit import Notification


class NotificationService:
    """站内消息：入库 + WS 实时推送（离线用户下次连接拉取）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def push(self, user_id: int, type: str, title: str, body: str | None = None) -> Notification:
        """创建站内消息（入库）。"""
        notif = Notification(user_id=user_id, type=type, title=title, body=body, is_read=False)
        self.db.add(notif)
        await self.db.commit()
        await self.db.refresh(notif)
        # TODO(M5 T5.19): 经 ws/hub.py 实时推送 8 频道
        return notif

    async def list_unread(self, user_id: int, limit: int = 20) -> list[Notification]:
        from sqlalchemy import select

        result = await self.db.execute(
            select(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .order_by(Notification.id.desc())
            .limit(limit)
        )
        return list(result.scalars())
