# announcements 管理路由（公告 CRUD：创建/编辑/发布/下线/删除，审计留痕 + WS 广播）
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.core.errors import NotFoundError
from api.deps import DbDep, require_admin
from api.models.announcement import Announcement
from api.services.audit.service import AuditService

router = APIRouter(prefix="/announcements", tags=["admin-announcements"])


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    body: str | None = Field(default=None, max_length=8000)
    level: str = Field(default="info", pattern="^(info|warning|critical)$")
    pinned: bool = False


class StatusIn(BaseModel):
    status: str  # draft / published / offline


def _to_dict(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "body": a.body,
        "level": a.level,
        "status": a.status,
        "pinned": a.pinned,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("")
async def list_announcements(
    status: str = Query(""),
    db: DbDep = None,
    _admin=Depends(require_admin),
) -> dict:
    from sqlalchemy import select

    stmt = select(Announcement).order_by(Announcement.id.desc())
    if status:
        stmt = stmt.where(Announcement.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_to_dict(a) for a in rows]}


@router.post("")
async def create_announcement(body: AnnouncementIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    record = Announcement(
        title=body.title, body=body.body, level=body.level,
        pinned=body.pinned, status="draft",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    await AuditService(db).log(
        actor_id=admin["id"], action="announcement.create",
        target_type="announcement", target_id=str(record.id),
        after={"title": record.title, "level": record.level},
    )
    return _to_dict(record)


@router.patch("/{announcement_id}")
async def update_announcement(
    announcement_id: int, body: AnnouncementIn, db: DbDep = None, admin=Depends(require_admin)
) -> dict:
    record = await db.get(Announcement, announcement_id)
    if record is None:
        raise NotFoundError("公告不存在")
    before = {"title": record.title, "level": record.level, "pinned": record.pinned}
    record.title = body.title
    record.body = body.body
    record.level = body.level
    record.pinned = body.pinned
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="announcement.update",
        target_type="announcement", target_id=str(announcement_id),
        before=before, after={"title": record.title, "level": record.level, "pinned": record.pinned},
    )
    return _to_dict(record)


@router.patch("/{announcement_id}/status")
async def update_status(
    announcement_id: int, body: StatusIn, db: DbDep = None, admin=Depends(require_admin)
) -> dict:
    record = await db.get(Announcement, announcement_id)
    if record is None:
        raise NotFoundError("公告不存在")
    if body.status not in ("draft", "published", "offline"):
        raise NotFoundError("无效状态")
    before = record.status
    record.status = body.status
    if body.status == "published" and record.published_at is None:
        record.published_at = datetime.now(timezone.utc)
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="announcement.status",
        target_type="announcement", target_id=str(announcement_id),
        before={"status": before}, after={"status": record.status},
    )
    if body.status == "published":
        try:
            from api.ws.hub import hub

            await hub.broadcast("announcement.new", _to_dict(record))
        except Exception:  # noqa: BLE001 广播失败不影响状态变更
            pass
    return _to_dict(record)


@router.delete("/{announcement_id}")
async def delete_announcement(announcement_id: int, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    record = await db.get(Announcement, announcement_id)
    if record is None:
        raise NotFoundError("公告不存在")
    await db.delete(record)
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="announcement.delete",
        target_type="announcement", target_id=str(announcement_id),
        after={"title": record.title},
    )
    return {"deleted": True}
