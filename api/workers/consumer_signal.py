# 信号消费（M3 T3.3：订阅 signal.new → CopyEngine 处理）
from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis

from api.core.config import get_settings
from api.workers.celery_app import celery_app

logger = logging.getLogger("signal-saas.workers.copy")

TOPIC_SIGNAL_NEW = "signal.new"


@celery_app.task(name="copy.process_signal")
def process_signal_task(signal_id: int) -> str:
    """Celery 任务：处理单条信号（供消费器调用）。"""
    import asyncio as _asyncio

    from api.db.session import get_session_factory
    from api.services.copyengine.service import CopyEngine

    async def _run() -> str:
        factory = get_session_factory()
        async with factory() as db:
            from api.models.signal import SourceSignal

            sig = await db.get(SourceSignal, signal_id)
            if sig is None or sig.dropped:
                return f"signal {signal_id}: skipped (missing/dropped)"
            engine = CopyEngine(db)
            orders = await engine.handle_signal(sig)
            await db.commit()
            return f"signal {signal_id}: {len(orders)} orders"

    try:
        return _asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        logger.exception("process signal %s failed: %s", signal_id, exc)
        raise


async def consume_signal_events() -> None:
    """阻塞消费 Redis Pub/Sub `signal.new`（dev 直跑；生产由 Celery 触发）。"""
    settings = get_settings()
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(TOPIC_SIGNAL_NEW)
    logger.info("subscribed to %s", TOPIC_SIGNAL_NEW)
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            if data.get("dropped"):
                logger.info("signal dropped event: %s", data.get("reason"))
                continue
            process_signal_task.delay(int(data["id"]))
        except Exception as exc:  # noqa: BLE001
            logger.error("consume error: %s", exc)
