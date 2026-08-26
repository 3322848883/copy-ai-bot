"""跨进程 WebSocket 事件桥：Celery worker -> Redis -> API WsHub。"""
from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis

from api.core.config import get_settings
from api.ws.hub import hub

logger = logging.getLogger("signal-saas.ws.broker")
WS_EVENT_TOPIC = "ws.events"


async def publish_user_event(user_id: int, channel: str, payload: dict) -> None:
    """跨进程发布用户事件；推送故障不得回滚已经完成的交易。"""
    redis = aioredis.from_url(
        get_settings().redis_url, decode_responses=True,
        socket_connect_timeout=0.3, socket_timeout=0.3,
    )
    try:
        await redis.publish(
            WS_EVENT_TOPIC,
            json.dumps(
                {"user_id": int(user_id), "channel": channel, "data": payload},
                ensure_ascii=False,
                default=str,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ws event publish failed user=%s channel=%s: %s", user_id, channel, exc)
    finally:
        await redis.aclose()


async def _bridge_loop() -> None:
    """API 进程订阅 Redis，并转发给本进程持有的真实 WebSocket 连接。"""
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(WS_EVENT_TOPIC)
    logger.info("websocket event bridge subscribed to %s", WS_EVENT_TOPIC)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                event = json.loads(message["data"])
                await hub.push(
                    int(event["user_id"]), str(event["channel"]), event.get("data") or {},
                )
            except Exception as exc:  # noqa: BLE001 单条坏消息不终止桥
                logger.warning("ws event bridge dropped malformed event: %s", exc)
    finally:
        try:
            await pubsub.unsubscribe(WS_EVENT_TOPIC)
            await pubsub.aclose()
        finally:
            await redis.aclose()


async def start_ws_event_bridge() -> asyncio.Task:
    return asyncio.create_task(_bridge_loop(), name="ws-event-bridge")
