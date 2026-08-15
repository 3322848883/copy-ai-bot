# audit 模块（M1 T1.10）
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.audit import AuditEvent


class AuditService:
    """后台操作审计：写操作全量留痕（不可删除）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        *,
        actor_id: int,
        action: str,
        target_type: str,
        target_id: str,
        before: dict | None = None,
        after: dict | None = None,
        reason: str | None = None,
        ip: str | None = None,
    ) -> AuditEvent:
        """写入一条审计记录（before/after 序列化为 JSON 存储）。"""
        event = AuditEvent(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            before=json.dumps(before, ensure_ascii=False) if before is not None else None,
            after=json.dumps(after, ensure_ascii=False) if after is not None else None,
            reason=reason,
            ip=ip,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def list_recent(self, limit: int = 50) -> list[AuditEvent]:
        from sqlalchemy import select

        result = await self.db.execute(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit))
        return list(result.scalars())
