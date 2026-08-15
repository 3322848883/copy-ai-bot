# 各频道消息推送 handler（M5 T5.19 完善）
from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from api.ws.channels import CHANNELS
from api.ws.hub import hub

logger = logging.getLogger("signal-saas.ws")


async def handle_ws(ws: WebSocket, user_id: int) -> None:
    """WebSocket 连接生命周期：注册 → hello → 心跳 → 断开清理。

    客户端可发送 {"type":"ping"} 保活，服务端回 {"type":"pong"}；
    其余消息忽略（预留频道订阅扩展）。
    """
    await hub.connect(user_id, ws)
    try:
        await ws.send_text(
            json.dumps(
                {"channel": "hello", "data": {"user_id": user_id, "channels": list(CHANNELS)}},
                ensure_ascii=False,
            )
        )
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 连接异常断开
        logger.debug("ws connection error user=%s", user_id)
    finally:
        await hub.disconnect(user_id, ws)
