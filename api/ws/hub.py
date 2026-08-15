# WebSocket Hub：连接管理、房间订阅（M5 T5.19 完善）
from __future__ import annotations

import json
import logging

logger = logging.getLogger("signal-saas.ws")


class WsHub:
    """按 user_id 归入房间，推送 8 频道消息。

    - 每个 user_id 可持有多个连接（多标签页/多设备）
    - push 对失效连接自动清理，不抛异常
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[object]] = {}

    async def connect(self, user_id: int, ws) -> None:
        self._connections.setdefault(user_id, set()).add(ws)

    async def disconnect(self, user_id: int, ws) -> None:
        conns = self._connections.get(user_id)
        if conns:
            conns.discard(ws)
            if not conns:
                self._connections.pop(user_id, None)

    async def push(self, user_id: int, channel: str, payload: dict) -> None:
        """推送给在线连接；离线用户下次连接拉取站内消息。"""
        conns = self._connections.get(user_id)
        if not conns:
            return
        message = json.dumps({"channel": channel, "data": payload}, ensure_ascii=False, default=str)
        dead: list[object] = []
        for ws in list(conns):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001 连接已断开
                dead.append(ws)
        for ws in dead:
            conns.discard(ws)
        if dead and not conns:
            self._connections.pop(user_id, None)

    def online_user_ids(self) -> list[int]:
        """当前在线用户列表（供 pnl.tick 周期任务使用）。"""
        return [uid for uid, conns in self._connections.items() if conns]


# 全局单例：服务层直接 import 推送业务事件
hub = WsHub()
