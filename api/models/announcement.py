"""Announcement 模型（平台公告）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base, TimestampMixin


class Announcement(TimestampMixin, Base):
    """平台公告：管理端发布，前台横幅/列表展示，可置顶。"""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(String(16), default="info")  # info / warning / critical
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft / published / offline
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
