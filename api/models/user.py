"""User / Identity / IdentityExchange / ApiKey 模型（设计 §4.2）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # CITEXT 由迁移保证
    password_hash: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(32), default="user")  # user / admin / reviewer / support
    risk_disclosure_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # ★ T1.7
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # ★ 后台用户管理「备注」

    identity: Mapped["Identity"] = relationship(back_populates="user", uselist=False, foreign_keys="Identity.user_id")


class Identity(TimestampMixin, Base):
    __tablename__ = "identities"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16), nullable=True)          # gate/binance/...
    invite_code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 好友邀请码
    exchange_invite_code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # ★ G27
    inviter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    identity_type: Mapped[str] = mapped_column(String(16), default="normal")  # normal / sub_account
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="identity", foreign_keys="Identity.user_id")


class IdentityExchange(Base):
    __tablename__ = "identity_exchanges"

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_user_id: Mapped[int] = mapped_column(ForeignKey("identities.user_id"))
    exchange: Mapped[str] = mapped_column(String(16))
    api_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(16))
    ciphertext: Mapped[str] = mapped_column(Text)
    nonce: Mapped[str] = mapped_column(String(64))
    tag: Mapped[str] = mapped_column(String(64))
    aad: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "exchange", name="uq_api_key_user_exchange"),)
