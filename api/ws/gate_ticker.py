# Gate WS 实时行情（模拟盘 mark_price 实时刷新）
# ★ 2026-08-24：Gate 官方 WebSocket 支持 futures.tickers 实时推送（wss://fx-ws.gateio.ws/v4/ws/usdt）。
#   订阅模拟盘当前持仓的合约，逐 tick 更新 PositionSnapshot.mark_price + 未实现盈亏；
#   REST 兜底任务（paper.update_marks）保证 WS 断线期间价格仍新鲜。
from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets
from sqlalchemy import select

from api.core.config import get_settings
from api.db.session import get_session_factory
from api.models.bot import CopyBot, PositionSnapshot
from api.services.paperbroker.service import PaperBroker

logger = logging.getLogger("signal-saas.ws.gate_ticker")

GATE_WS_URL = "wss://fx-ws.gateio.ws/v4/ws/usdt"
RECONNECT_DELAY = 5.0
RECONNECT_MAX = 60.0
SYNC_INTERVAL = 30.0   # 订阅符号与持仓对账周期（秒）
RECV_TIMEOUT = 5.0     # 单次 recv 超时，用于周期对账与心跳


def _ws_proxy() -> str | None:
    """★ 2026-08-24：fx-ws.gateio.ws 部分网络不可直连，经配置的 HTTP 代理（CONNECT）连接。"""
    proxy = get_settings().gate_ws_proxy_url.strip()
    return proxy or None


def _gate_contract(symbol: str) -> str:
    """快照存储符号（GUAUSDT）→ Gate 合约名（GUA_USDT）。"""
    s = (symbol or "").strip().upper()
    if "_" in s:
        return s
    if s.endswith("USDT") and len(s) > 4:
        return s[:-4] + "_USDT"
    return s


def _stored_symbol(contract: str) -> str:
    """Gate 合约名（GUA_USDT）→ 快照存储符号（GUAUSDT）。"""
    return (contract or "").replace("_", "")


async def _open_paper_symbols(db) -> set[str]:
    rows = (
        await db.execute(
            select(PositionSnapshot.symbol)
            .join(CopyBot, CopyBot.id == PositionSnapshot.bot_id)
            .where(
                CopyBot.paper == True,  # noqa: E712
                PositionSnapshot.is_open == True,  # noqa: E712
            )
        )
    ).scalars().all()
    return {r for r in rows}


async def _subscribe(ws, symbols: set[str]) -> None:
    if not symbols:
        return
    logger.info("gate ws subscribe: %s", sorted(_gate_contract(s) for s in symbols))
    await ws.send(
        json.dumps(
            {
                "time": int(time.time()),
                "channel": "futures.tickers",
                "event": "subscribe",
                "payload": sorted(_gate_contract(s) for s in symbols),
            }
        )
    )


async def _run() -> None:
    subscribed: set[str] = set()
    delay = RECONNECT_DELAY
    factory = get_session_factory()
    while True:
        try:
            async with websockets.connect(
                GATE_WS_URL,
                proxy=_ws_proxy(),
                ping_interval=20,
                ping_timeout=20,
                open_timeout=15,
                max_size=2**20,
            ) as ws:
                logger.info("gate ws connected")
                delay = RECONNECT_DELAY
                last_sync = 0.0
                while True:
                    now = time.monotonic()
                    if now - last_sync >= SYNC_INTERVAL:
                        last_sync = now
                        async with factory() as db:
                            wanted = await _open_paper_symbols(db)
                        if wanted != subscribed:
                            await _subscribe(ws, wanted)
                            subscribed = wanted
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
                    except asyncio.TimeoutError:
                        continue
                    msg = json.loads(raw)
                    if msg.get("channel") != "futures.tickers" or msg.get("event") != "update":
                        continue
                    prices: dict[str, float] = {}
                    for t in msg.get("result") or []:
                        try:
                            last = float(t.get("last") or 0)
                        except (TypeError, ValueError):
                            continue
                        if last > 0:
                            prices[_stored_symbol(t.get("contract", ""))] = last
                    if prices:
                        async with factory() as db:
                            updated = await PaperBroker(db).update_marks(prices)
                        if updated:
                            logger.info("gate ws update_marks: %d positions", updated)
        except Exception:  # noqa: BLE001 断线/解析失败重连，不影响 API 服务
            logger.warning("gate ws error, reconnect in %.0fs", delay, exc_info=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX)


async def start_gate_ticker() -> asyncio.Task:
    task = asyncio.create_task(_run(), name="gate-ticker")
    return task
