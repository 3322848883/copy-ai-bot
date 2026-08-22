"""SourceSignal / Trader / Strategy / TraderProfile 模型（§4.2，G03/G05）。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base, TimestampMixin


class SourceSignal(TimestampMixin, Base):
    """标准化信号（★ G03：action 字段，dedupe_key 含 action；T2.4 dropped 异常丢弃）。"""

    __tablename__ = "source_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    source_trader_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))  # long / short
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    qty: Mapped[float] = mapped_column(Float)
    # ★ 带单员持仓占比（leader 该 symbol 占其组合比例，∈[0,1]，如 0.20=20%）
    #   真实 feed 用其做 qty 换算（percent × 保证金）；批量/WS 无此信息为 None
    percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    action: Mapped[str] = mapped_column(String(8))  # open / add / reduce / close（★ G03）
    source_mode: Mapped[str] = mapped_column(String(1), default="A")  # A=爬虫 / B=WS
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True)
    dropped: Mapped[bool] = mapped_column(default=False)  # ★ T2.4 异常丢弃标记
    drop_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 丢弃原因


class Trader(Base):
    __tablename__ = "traders"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16))
    trader_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)  # ★ 真实信号源：带单员昵称
    followers: Mapped[int] = mapped_column(Integer, default=0)  # ★ 真实信号源：跟单人数
    # ★ 带单员是否隐藏当前持仓（Gate config.is_hide）：True → 公开采集拿不到仓位，
    #   上架只能走模式B（API 镜像跟单）；None=尚未采集到（detail 未拉过）
    hide_position: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (UniqueConstraint("exchange", "trader_id", name="uq_trader_exchange_id"),)


class Strategy(TimestampMixin, Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id"))
    source_exchange: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(64))
    style: Mapped[str] = mapped_column(String(16))  # trend / range / momentum
    risk_rating: Mapped[str] = mapped_column(String(8))  # low / mid / high
    # ★ M6 T6.1 灰度发布：新策略默认 20%，按 user 哈希放量
    gray_pct: Mapped[int] = mapped_column(Integer, default=100)  # 0-100
    status: Mapped[str] = mapped_column(String(16), default="listed")  # listed / paused / delisted
    # ★ 策略来源：A=公开广场采集/G04 审核上架（人工）；B=模式2 跟单同步自动上架。
    #   delist_unfollowed 只下架 B——否则模式2 同步会把模式1 审核上架的策略全部误下架。
    source: Mapped[str] = mapped_column(String(1), default="A", server_default="A")


class ClosedPosition(Base):
    """带单员已平仓记录（Gate close_position 接口）—— 策略详情页交易记录展示。

    纯展示数据，不入信号执行管道（区别于 source_signals）。
    ★ 对隐藏持仓交易员同样采集（历史平仓不受 is_hide 屏蔽），方向真实。
    gate_order_id 为 Gate 接口返回的平仓记录 id，跨轮去重键。
    """

    __tablename__ = "trader_closed_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id"), index=True)
    gate_order_id: Mapped[int] = mapped_column(BigInteger)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))  # long / short（真实方向）
    profit: Mapped[float | None] = mapped_column(Float, nullable=True)  # 已实现盈亏 USDT
    profit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 收益率（小数）
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    leverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("trader_id", "gate_order_id", name="uq_closed_pos_order"),)


class TraderProfile(Base):
    """每日画像快照（★ G05 扩展）。"""

    __tablename__ = "trader_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id"))
    snapshot_date: Mapped[date] = mapped_column(Date)
    roi_7d: Mapped[float] = mapped_column(Float, default=0)
    roi_30d: Mapped[float] = mapped_column(Float, default=0)
    roi_90d: Mapped[float] = mapped_column(Float, default=0)
    roi_all: Mapped[float] = mapped_column(Float, default=0)
    win_rate_30d: Mapped[float] = mapped_column(Float, default=0)
    win_rate_all: Mapped[float] = mapped_column(Float, default=0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0)
    trading_days: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("trader_id", "snapshot_date", name="uq_trader_profile_date"),)
