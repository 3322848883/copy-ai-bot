"""Exchange / ContractSpec / PlatformPool / ExchangeInviteCode 模型（§4.2 + G06/G08/G27）。"""
from __future__ import annotations


from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base, TimestampMixin


class Exchange(Base):
    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(16), unique=True)  # gate/binance/okx/bybit/bitget
    label: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ContractSpec(Base):
    """合约级精度参数（★ G08：面值/最小开仓量/精度均从本表查询）。"""

    __tablename__ = "contract_specs"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    face_value_usdt: Mapped[float] = mapped_column()
    min_size: Mapped[float] = mapped_column()
    size_precision: Mapped[int] = mapped_column()
    contract_type: Mapped[str] = mapped_column(String(32), default="USDT-margined")

    __table_args__ = (UniqueConstraint("exchange", "symbol", name="uq_contract_exchange_symbol"),)


class PlatformPool(TimestampMixin, Base):
    """平台资源池邀请码（★ G06：命中且交易所匹配 → 主号下级免订阅）。"""

    __tablename__ = "platform_pool"

    id: Mapped[int] = mapped_column(primary_key=True)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True)
    exchange: Mapped[str] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExchangeInviteCode(TimestampMixin, Base):
    """交易所邀请码（★ G27：每所多码，注册时核实）。"""

    __tablename__ = "exchange_invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / inactive
    remark: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bind_count: Mapped[int] = mapped_column(Integer, default=0)
    max_binds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None=不限

    __table_args__ = (UniqueConstraint("exchange", "code", name="uq_exchange_invite_code"),)
