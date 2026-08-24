# Gate 公开期货行情服务（免鉴权 REST，进程内短缓存）
# 供模拟盘成交价/实时 mark_price 更新使用；任何异常返回 None/空，绝不造假数据。
from __future__ import annotations

import asyncio
import logging
import time

import httpx

logger = logging.getLogger("signal-saas.prices")

GATE_API_BASE = "https://api.gateio.ws/api/v4"
PRICE_TTL = 8.0  # 秒：单符号缓存（WS 实时通道未覆盖时的 REST 兜底）

_cache: dict[str, tuple[float, float]] = {}  # symbol(带下划线) -> (fetched_at, last)
_lock = asyncio.Lock()


def _gate_symbol(symbol: str) -> str:
    """符号规范化：跟单/信号源接口用 'GUAUSDT'（无下划线），期货行情接口用 'GUA_USDT'。"""
    s = (symbol or "").strip().upper()
    if "_" in s:
        return s
    if s.endswith("USDT") and len(s) > 4:
        return s[:-4] + "_USDT"
    return s


async def fetch_futures_price(symbol: str) -> float | None:
    """获取单个合约最新价；命中缓存直接返回，失败返回 None。"""
    gsym = _gate_symbol(symbol)
    now = time.monotonic()
    hit = _cache.get(gsym)
    if hit and now - hit[0] < PRICE_TTL:
        return hit[1]
    async with _lock:
        hit = _cache.get(gsym)
        if hit and time.monotonic() - hit[0] < PRICE_TTL:
            return hit[1]
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                # ★ 2026-08-24：路径形式 /tickers/{contract} 返回 401（INVALID_CREDENTIALS），
                #   必须用查询参数 ?contract= 才免鉴权返回真实行情
                resp = await client.get(f"{GATE_API_BASE}/futures/usdt/tickers", params={"contract": gsym})
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    data = data[0] if data else {}
            last = float(data.get("last") or 0)
            if last <= 0:
                return None
            _cache[gsym] = (time.monotonic(), last)
            return last
        except Exception:  # noqa: BLE001 行情失败不影响业务
            logger.warning("fetch price %s failed", gsym)
            return None


async def fetch_futures_prices(symbols: list[str]) -> dict[str, float]:
    """批量获取最新价（并发），返回 {原符号: 价格}；失败的符号不出现。"""
    if not symbols:
        return {}
    results = await asyncio.gather(*(fetch_futures_price(s) for s in symbols), return_exceptions=True)
    out: dict[str, float] = {}
    for sym, res in zip(symbols, results):
        if isinstance(res, float) and res > 0:
            out[sym] = res
    return out
