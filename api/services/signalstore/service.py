# signalstore 模块（M2 T2.4：入库去重 + 异常丢弃 + Redis Pub/Sub）
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.models.signal import SourceSignal, Trader
from api.services.normalizer.service import NormalizedSignal

logger = logging.getLogger("signal-saas.signalstore")

TOPIC_SIGNAL_NEW = "signal.new"


class SignalStore:
    """标准化信号入库 + 二级去重 + 异常丢弃（★ 模式 A >10s）+ Redis 事件发布。"""

    def __init__(self, db: AsyncSession, redis: aioredis.Redis | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.redis = redis or aioredis.from_url(self.settings.redis_url, decode_responses=True)

    async def upsert_trader(self, exchange: str, trader_id: str, name: str | None = None, followers: int = 0) -> Trader:
        """确保 Trader 存在（幂等），并记录带单员昵称/跟单人数（真实信号源）。"""
        trader = await self.db.scalar(
            select(Trader).where(Trader.exchange == exchange, Trader.trader_id == trader_id)
        )
        if trader is None:
            trader = Trader(exchange=exchange, trader_id=trader_id, name=name, followers=followers)
            self.db.add(trader)
            await self.db.flush()
        else:
            changed = False
            if name and trader.name != name:
                trader.name = name
                changed = True
            if followers and trader.followers != followers:
                trader.followers = followers
                changed = True
            if changed:
                await self.db.flush()
        return trader

    async def ingest(self, ns: NormalizedSignal) -> SourceSignal:
        """入库单条标准化信号。

        - dedupe_key 已存在（DB 唯一约束）→ 丢弃
        - ★ 模式 A 延迟 >10s → 丢弃（dropped=true + drop_reason）
        - 成功 → SourceSignal 入库 + Redis Pub/Sub `signal.new`
        """
        dk = ns.dedupe_key()
        age_ms = (datetime.now(timezone.utc) - ns.opened_at).total_seconds() * 1000

        # ★ 异常丢弃：模式 A 延迟红线 10s（设计蓝本 §2.4）
        if ns.source_mode == "A" and age_ms > self.settings.delay_redline_mode_a_ms:
            sig = await self._insert_dropped(ns, dk, f"mode A age {age_ms:.0f}ms > {self.settings.delay_redline_mode_a_ms}ms")
            await self.redis.publish(TOPIC_SIGNAL_NEW, json.dumps({"dropped": True, "reason": sig.drop_reason}, ensure_ascii=False))
            return sig
        if ns.source_mode == "B" and age_ms > self.settings.delay_redline_mode_b_ms:
            sig = await self._insert_dropped(ns, dk, f"mode B age {age_ms:.0f}ms > {self.settings.delay_redline_mode_b_ms}ms")
            await self.redis.publish(TOPIC_SIGNAL_NEW, json.dumps({"dropped": True, "reason": sig.drop_reason}, ensure_ascii=False))
            return sig

        sig = SourceSignal(
            exchange=ns.exchange,
            source_trader_id=ns.source_trader_id,
            symbol=ns.symbol,
            side=ns.side,
            leverage=ns.leverage,
            qty=ns.qty,
            action=ns.action,
            source_mode=ns.source_mode,
            opened_at=ns.opened_at,
            received_at=ns.received_at,
            dedupe_key=dk,
            dropped=False,
        )
        self.db.add(sig)
        try:
            await self.db.commit()
        except IntegrityError:
            # dedupe_key 已存在 → 静默丢弃
            await self.db.rollback()
            logger.info("duplicate signal dropped: %s", dk[:16])
            sig.dropped = True
            sig.drop_reason = "duplicate(dedupe_key)"
            return sig
        await self.db.refresh(sig)

        # ★ M6 T6.2：信号源监控打点（signal_received_total）
        from api.core import metrics as M

        M.signal_received_total.labels(exchange=ns.exchange, source=ns.source_mode).inc()

        # Redis Pub/Sub 事件（M3 copy-engine 订阅）
        await self.redis.publish(
            TOPIC_SIGNAL_NEW,
            json.dumps(
                {
                    "id": sig.id,
                    "exchange": sig.exchange,
                    "trader": sig.source_trader_id,
                    "symbol": sig.symbol,
                    "side": sig.side,
                    "action": sig.action,
                    "leverage": sig.leverage,
                    "qty": sig.qty,
                    "opened_at": sig.opened_at.isoformat(),
                    "dropped": False,
                },
                ensure_ascii=False,
            ),
        )
        return sig

    async def _insert_dropped(self, ns: NormalizedSignal, dk: str, reason: str) -> SourceSignal:
        """写入 dropped 记录（dropped=true）。"""
        sig = SourceSignal(
            exchange=ns.exchange,
            source_trader_id=ns.source_trader_id,
            symbol=ns.symbol,
            side=ns.side,
            leverage=ns.leverage,
            qty=ns.qty,
            action=ns.action,
            source_mode=ns.source_mode,
            opened_at=ns.opened_at,
            received_at=ns.received_at,
            dedupe_key=dk,
            dropped=True,
            drop_reason=reason,
        )
        self.db.add(sig)
        try:
            await self.db.commit()
            await self.db.refresh(sig)
        except IntegrityError:
            # dedupe_key 已存在 → rollback 后 sig 已脱离 session，不再 refresh（属性仍保留）
            await self.db.rollback()
            sig.dropped = True
            sig.drop_reason = "duplicate(dedupe_key)"
        logger.warning("signal dropped: %s (%s)", ns.source_trader_id, reason)
        return sig
