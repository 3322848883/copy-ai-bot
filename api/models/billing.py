"""Subscription / PaymentOrder / Reward / Withdrawal / Invite 模型（§4.2，G09/G11/G12/G13）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base, TimestampMixin


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String(32))  # trial_5u / monthly_19_9u
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / active / expired
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payment_order_id: Mapped[int | None] = mapped_column(ForeignKey("payment_orders.id"), nullable=True)


class PaymentOrder(TimestampMixin, Base):
    """支付订单（★ G09：三链即时校验）。"""

    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String(32))
    amount_usdt: Mapped[float] = mapped_column(Float)
    # ★ H4：链上实际到账金额（用户可能多付，如 2U 扣手续费到账 1.96 → 订单 1.0）
    paid_amount_usdt: Mapped[float | None] = mapped_column(Float, nullable=True)
    network: Mapped[str] = mapped_column(String(8))  # trc20 / bep20 / erc20
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # pending / verifying / polling / confirmed / failed / manual / timeout / expired
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    required_confirmations: Mapped[int] = mapped_column(Integer, default=12)
    poll_attempts: Mapped[int] = mapped_column(Integer, default=0)


class Reward(TimestampMixin, Base):
    """邀请奖励（★ G11：verifying_ends_at 48h 风控延长）。"""

    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source_payment_order_id: Mapped[int] = mapped_column(ForeignKey("payment_orders.id"))
    # ★ 生产修复：锁定资金归属于具体提现单，避免并发提现互相解锁/误发
    withdrawal_id: Mapped[int | None] = mapped_column(ForeignKey("withdrawals.id"), nullable=True, index=True)
    amount_usdt: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="verifying")
    # verifying / available / withdrawing / paid / frozen / canceled / paid_failed / rolled_back
    verifying_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verifying_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Withdrawal(TimestampMixin, Base):
    """提现（★ G13：10U 门槛 + 1U 手续费）。"""

    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_usdt: Mapped[float] = mapped_column(Float)
    fee_usdt: Mapped[float] = mapped_column(Float, default=1.0)
    network: Mapped[str] = mapped_column(String(8))
    address: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="pending_review")
    # pending_review / approved / processing / paid / rejected / canceled / expired
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Invite(TimestampMixin, Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    code: Mapped[str] = mapped_column(String(32))
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked: Mapped[bool] = mapped_column(Integer, default=False)


class PlatformAddress(TimestampMixin, Base):
    """平台 USDT 收款地址（后台管理，支付校验时读取 active 项）。"""

    __tablename__ = "platform_addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    network: Mapped[str] = mapped_column(String(8), index=True)  # trc20 / bep20 / erc20
    address: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / inactive
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
