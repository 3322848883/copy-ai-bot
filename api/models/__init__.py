"""ORM 模型统一出口（注册到 Base.metadata，供 Alembic 与代码使用）。"""
from api.models.user import User, Identity, IdentityExchange, ApiKey
from api.models.exchange import (
    Exchange,
    ContractSpec,
    PlatformPool,
    ExchangeInviteCode,
)
from api.models.signal import SourceSignal, Trader, Strategy, TraderProfile
from api.models.bot import CopyBot, CopyOrder, PositionSnapshot
from api.models.billing import (
    Subscription,
    PaymentOrder,
    Reward,
    Withdrawal,
    Invite,
    PlatformAddress,
)
from api.models.audit import AuditEvent, Notification
from api.models.announcement import Announcement

__all__ = [
    "User",
    "Identity",
    "IdentityExchange",
    "ApiKey",
    "Exchange",
    "ContractSpec",
    "PlatformPool",
    "ExchangeInviteCode",
    "SourceSignal",
    "Trader",
    "Strategy",
    "TraderProfile",
    "CopyBot",
    "CopyOrder",
    "PositionSnapshot",
    "Subscription",
    "PaymentOrder",
    "Reward",
    "Withdrawal",
    "Invite",
    "PlatformAddress",
    "AuditEvent",
    "Notification",
    "Announcement",
]
