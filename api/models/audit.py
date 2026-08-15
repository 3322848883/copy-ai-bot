"""AuditEvent / Notification 模型（§3.19/§3.20）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base, TimestampMixin


class AuditEvent(Base):
    """后台操作审计（写操作全量留痕，不可删除）。"""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))      # 如 withdrawal.approve
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[str | None] = mapped_column(Text, nullable=True)   # 变更前 JSON
    after: Mapped[str | None] = mapped_column(Text, nullable=True)    # 变更后 JSON
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Notification(TimestampMixin, Base):
    """站内消息（WS 实时推送，离线拉取）。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))  # reward_available / payment_timeout / ...
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
