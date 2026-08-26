"""生产跟单链路只读诊断：信号 → 机器人 → 订单 → Redis 差分基线。

容器内运行：python scripts/diagnose_copy_pipeline.py
不解密、不输出任何 API Key；不修改数据库或 Redis。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select

from api.core.config import get_settings
from api.db.session import get_session_factory
from api.models.bot import CopyBot, CopyOrder
from api.models.signal import SourceSignal, Strategy, Trader
from api.models.user import ApiKey


def _iso(value):
    return value.isoformat() if value else None


async def diagnose() -> dict:
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_bots": [],
        "recent_signals": [],
        "recent_orders": [],
        "redis_feed_states": [],
    }
    factory = get_session_factory()
    async with factory() as db:
        bots = (
            await db.execute(
                select(CopyBot, Strategy, Trader, ApiKey)
                .join(Strategy, Strategy.id == CopyBot.strategy_id)
                .join(Trader, Trader.id == Strategy.trader_id)
                .join(ApiKey, ApiKey.id == CopyBot.api_key_id)
                .where(CopyBot.status == "active")
                .order_by(CopyBot.id.desc())
            )
        ).all()
        for bot, strategy, trader, api_key in bots:
            report["active_bots"].append({
                "bot_id": bot.id,
                "user_id": bot.user_id,
                "paper": bool(bot.paper),
                "exchange": bot.exchange,
                "strategy_id": strategy.id,
                "strategy_status": strategy.status,
                "follow_enabled": bool(strategy.follow_enabled),
                "gray_pct": strategy.gray_pct,
                "source_mode": strategy.source,
                "trader_id": trader.trader_id,
                "api_key_status": api_key.status,
            })

        signals = (
            await db.execute(select(SourceSignal).order_by(SourceSignal.id.desc()).limit(30))
        ).scalars().all()
        for sig in signals:
            report["recent_signals"].append({
                "id": sig.id,
                "trader_id": sig.source_trader_id,
                "symbol": sig.symbol,
                "side": sig.side,
                "action": sig.action,
                "mode": sig.source_mode,
                "source_at": _iso(sig.opened_at),
                "received_at": _iso(sig.received_at),
                "dropped": bool(sig.dropped),
                "drop_reason": sig.drop_reason,
            })

        orders = (
            await db.execute(
                select(CopyOrder, CopyBot, SourceSignal)
                .join(CopyBot, CopyBot.id == CopyOrder.bot_id)
                .join(SourceSignal, SourceSignal.id == CopyOrder.signal_id)
                .order_by(CopyOrder.id.desc())
                .limit(30)
            )
        ).all()
        for order, bot, sig in orders:
            report["recent_orders"].append({
                "id": order.id,
                "bot_id": bot.id,
                "signal_id": sig.id,
                "symbol": sig.symbol,
                "action": order.action,
                "status": order.status,
                "failure_category": order.failure_category,
                "fail_reason": order.fail_reason,
                "qty": order.qty,
                "created_at": _iso(order.created_at),
                "executed_at": _iso(order.executed_at),
            })

    try:
        import redis.asyncio as aioredis

        redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            async for key in redis.scan_iter(match="gate:feed:state:*"):
                raw = await redis.get(key)
                try:
                    value = json.loads(raw) if raw else None
                except (TypeError, ValueError):
                    value = raw
                report["redis_feed_states"].append({"key": key, "value": value})
        finally:
            await redis.aclose()
    except Exception as exc:  # 诊断脚本应继续输出 DB 结果
        report["redis_error"] = f"{type(exc).__name__}: {exc}"
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(diagnose()), ensure_ascii=False, indent=2))
