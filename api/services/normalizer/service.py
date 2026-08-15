# normalizer 模块（M2 T2.2：信号标准化 + 去重）
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

VALID_SIDES = ("long", "short")
VALID_ACTIONS = ("open", "add", "reduce", "close")  # ★ G03


class NormalizedSignal(BaseModel):
    """标准化信号（与设计蓝本 §2.3 一致，★ G03 action 字段）。"""

    exchange: str
    source_trader_id: str
    symbol: str
    side: str  # long / short
    leverage: int = Field(default=1, ge=1, le=125)
    qty: float = Field(ge=0)
    action: str = "open"  # open / add / reduce / close（★ G03）
    source_mode: str = "A"  # A=爬虫 / B=WS
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict = Field(default_factory=dict, exclude=True)

    @field_validator("side")
    @classmethod
    def _side(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in VALID_SIDES:
            raise ValueError(f"side 必须为 {VALID_SIDES}")
        return v

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in VALID_ACTIONS:
            raise ValueError(f"action 必须为 {VALID_ACTIONS}")
        return v

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, v: str) -> str:
        return v.strip().upper().replace("-", "")

    def dedupe_key(self) -> str:
        """★ G03：exchange|trader|symbol|side|action|opened_at(秒级)。"""
        ts = self.opened_at.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
        raw = f"{self.exchange}|{self.source_trader_id}|{self.symbol}|{self.side}|{self.action}|{ts}"
        return hashlib.sha256(raw.encode()).hexdigest()[:64]


@dataclass
class NormalizeResult:
    """单条原始记录标准化结果（有效/丢弃）。"""

    signal: NormalizedSignal | None = None
    dedupe_key: str | None = None
    dropped: bool = False
    drop_reason: str = ""
    drops: list[str] = field(default_factory=list)  # 错误明细


class SignalNormalizer:
    """原始信号 → NormalizedSignal。

    丢弃规则（设计蓝本 §2.3）：
    - 必填字段缺失 / 非法
    - qty <= 0（close 除外，允许平仓信号 qty=0 表示全平）
    - 动作不合法
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()  # 内存二级缓存（重启清空）

    def normalize(self, raw: dict) -> NormalizeResult:
        """标准化单条原始信号。"""
        drops: list[str] = []

        def bad(reason: str) -> NormalizeResult:
            return NormalizeResult(dropped=True, drop_reason=reason, drops=drops)

        exchange = str(raw.get("exchange", "")).strip().lower()
        if not exchange:
            return bad("exchange 缺失")
        trader = str(raw.get("source_trader_id", "")).strip()
        if not trader:
            return bad("source_trader_id 缺失")
        symbol = str(raw.get("symbol", "")).strip().upper()
        if not symbol:
            return bad("symbol 缺失")
        side = str(raw.get("side", "")).strip().lower()
        if side not in VALID_SIDES:
            return bad(f"side 非法: {side}")

        try:
            leverage = int(raw.get("leverage", 1) or 1)
            qty = float(raw.get("qty", 0) or 0)
        except (TypeError, ValueError):
            return bad("qty/leverage 非数字")

        action = str(raw.get("action", "open")).strip().lower()
        if action not in VALID_ACTIONS:
            return bad(f"action 非法: {action}")
        # ★ 真实信号源画像级信号 qty=0（Gate 占比接口无数量）；负数仍拒绝
        if qty < 0 or (qty <= 0 and action not in ("open", "add", "close")):
            return bad(f"qty<=0 且 action={action}，非有效信号")

        try:
            opened = raw.get("opened_at")
            if isinstance(opened, datetime):
                opened_at = opened
            elif isinstance(opened, str) and opened:
                opened_at = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            else:
                opened_at = datetime.now(timezone.utc)
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=timezone.utc)
        except ValueError:
            return bad("opened_at 格式非法")

        signal = NormalizedSignal(
            exchange=exchange,
            source_trader_id=trader,
            symbol=symbol,
            side=side,
            leverage=leverage,
            qty=qty,
            action=action,
            source_mode=str(raw.get("source_mode", "A")),
            opened_at=opened_at,
            received_at=datetime.now(timezone.utc),
            raw=raw,
        )
        dk = signal.dedupe_key()
        if dk in self._seen:  # 内存二级缓存去重
            return NormalizeResult(dropped=True, drop_reason="duplicate(in-memory)", drops=drops)
        self._seen.add(dk)
        return NormalizeResult(signal=signal, dedupe_key=dk)
