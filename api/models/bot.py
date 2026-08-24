"""CopyBot / CopyOrder / PositionSnapshot 模型（§4.2，G03/G07）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base, TimestampMixin


class CopyBot(TimestampMixin, Base):
    __tablename__ = "copy_bots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"))
    exchange: Mapped[str] = mapped_column(String(16))
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"))
    amount_mode: Mapped[str] = mapped_column(String(16), default="percent")  # fixed / percent
    fixed_amount_usdt: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    leverage: Mapped[int] = mapped_column(Integer, default=10)
    margin_mode: Mapped[str] = mapped_column(String(16), default="isolated")  # isolated / cross（★ G07）
    max_total_position_usdt: Mapped[float] = mapped_column(Float, default=10_000)
    virtual_locked_usdt: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / paused / stopped
    # ★ M6 T6.2 沙箱：模拟盘不触达真实交易所
    paper: Mapped[bool] = mapped_column(Boolean, default=False)


class CopyOrder(Base):
    """跟单订单（★ G03：action + failure_category 枚举）。"""

    __tablename__ = "copy_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("copy_bots.id"), index=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("source_signals.id"))
    action: Mapped[str] = mapped_column(String(8))  # open / add / reduce / close
    qty: Mapped[float] = mapped_column(Float)
    leverage: Mapped[int] = mapped_column(Integer)
    required_margin_usdt: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    failure_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # balance / permission / leverage / symbol / min_size / network / price_deviation / slippage / risk / no_position / other
    # ★ 失败原因文本（2026-08-20）：category 只是 11 值枚举，管理员要看具体原因——
    #   ExecResult.reason / 风控规则名 / sizer 校验消息原样落库（截断 255）
    fail_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ★ 落库（下单尝试）时刻：executed_at 仅成交时写入，失败/待定订单此前无任何时间可展示
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PositionSnapshot(TimestampMixin, Base):
    __tablename__ = "position_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("copy_bots.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    mark_price: Mapped[float] = mapped_column(Float)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0)
    # ★ 已实现盈亏（2026-08-24）：减仓/平仓时累计，供 snapshot_pnl 聚合。
    #   此前平仓不记录，模拟盘/实盘已实现盈亏恒为 0。
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)
    # ★ 合约面值（2026-08-24）：落库时写入，update_marks 直接读（避免 notional/qty 推导出 face×price）
    face_value: Mapped[float] = mapped_column(Float, default=1.0)
    notional_usdt: Mapped[float] = mapped_column(Float, default=0)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
