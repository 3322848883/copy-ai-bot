# ws 路由（M5 T5.19：鉴权订阅 + 心跳）
from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket

from api.core.config import get_settings
from api.core.security import decode_token
from api.ws.handlers import handle_ws

router = APIRouter()


@router.websocket("/stream")
async def ws_stream(ws: WebSocket, token: str = Query("")) -> None:
    """WebSocket 实时推送入口：token 取 httpOnly cookie（同域）优先，query 兜底（dev）。

    鉴权失败关闭 4001；成功后进入 handler 生命周期。
    """
    await ws.accept()
    try:
        token = token or ws.cookies.get("ss_access") or ""
        if not token:
            await ws.close(code=4001)
            return
        payload = decode_token(token, get_settings().jwt_audience)
        if payload.get("type") != "access":
            await ws.close(code=4001)
            return
        user_id = int(payload["sub"])
    except Exception:  # noqa: BLE001 无效/过期 token
        await ws.close(code=4001)
        return
    await handle_ws(ws, user_id)
