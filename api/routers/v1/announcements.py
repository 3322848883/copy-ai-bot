# announcements 路由（用户端：已发布公告列表，公开）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import DbDep
from api.models.announcement import Announcement

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("")
async def list_announcements(limit: int = Query(20, ge=1, le=50), db: DbDep = None) -> dict:
    """已发布公告（置顶优先，发布时间倒序）。无需登录。"""
    from sqlalchemy import select

    stmt = (
        select(Announcement)
        .where(Announcement.status == "published")
        .order_by(Announcement.pinned.desc(), Announcement.published_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": a.id,
                "title": a.title,
                "body": a.body,
                "level": a.level,
                "pinned": a.pinned,
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a in rows
        ]
    }
