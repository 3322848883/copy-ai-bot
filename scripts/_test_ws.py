"""WS 端到端验证：鉴权订阅 + hello + pnl.tick 推送。"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///c:/Users/w6485/Desktop/AI 量化/信号聚合AI/dev.db"

import websockets
from api.core.security import create_token

WS_URL = "ws://127.0.0.1:8000/ws/stream"


async def main():
    # 1. 有效 token → hello
    token = create_token("10000", audience="web")
    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print("HELLO:", hello["channel"], "channels=", len(hello["data"]["channels"]))
        # 心跳
        await ws.send(json.dumps({"type": "ping"}))
        pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print("PONG:", pong)
        # 等待 pnl.tick（ticker 每 8s 推一次）
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=12))
            print("PUSH:", msg["channel"], json.dumps(msg["data"], ensure_ascii=False)[:200])
        except asyncio.TimeoutError:
            print("PUSH: timeout (no ticker)")

    # 2. 无效 token → 关闭 4001
    try:
        async with websockets.connect(f"{WS_URL}?token=bad-token") as ws:
            await ws.recv()
        print("BAD TOKEN: NOT closed (unexpected)")
    except websockets.exceptions.ConnectionClosed as e:
        print("BAD TOKEN: closed code =", e.rcvd.code if e.rcvd else e.code)


asyncio.run(main())
