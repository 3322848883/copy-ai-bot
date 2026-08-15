# scraper 模块（M2 T2.1：Gate 公开爬虫调度）
from __future__ import annotations

import logging
from typing import AsyncIterator

from api.services.normalizer.service import NormalizedSignal, SignalNormalizer
from api.services.scraper.adapters.gate import GateScraper, RawPosition, RawTrader

logger = logging.getLogger("signal-saas.scraper")


class ScraperService:
    """公开带单广场采集调度：排行榜 → 持仓 → 标准化 → 交给 signal-store。"""

    def __init__(self, normalizer: SignalNormalizer | None = None) -> None:
        self.normalizer = normalizer or SignalNormalizer()
        self.gate = GateScraper()
        self.adapters = {"gate": self.gate}

    async def scrape(self, exchange: str = "gate", limit: int = 100) -> int:
        """采集指定交易所，返回生成的有效信号数。"""
        adapter = self.adapters.get(exchange)
        if adapter is None:
            logger.warning("exchange %s 暂无适配器", exchange)
            return 0
        count = 0
        async for trader, positions in self._iter_trader_signals(adapter, limit):
            count += 1
        return count

    async def _iter_trader_signals(
        self, adapter: GateScraper, limit: int
    ) -> AsyncIterator[NormalizedSignal]:
        async for trader, positions in adapter.scrape_all_traders(limit):
            for pos in positions:
                ns = self._to_signal(trader, pos)
                if ns is None:
                    continue
                yield ns

    def _to_signal(self, trader: RawTrader, pos: RawPosition) -> NormalizedSignal | None:
        """持仓 → 标准化信号（open 动作）。"""
        result = self.normalizer.normalize(
            {
                "exchange": "gate",
                "source_trader_id": trader.trader_id,
                "symbol": pos.symbol,
                "side": pos.side,
                "leverage": pos.leverage,
                "qty": pos.qty,
                "action": "open",
                "source_mode": "A",
                "opened_at": pos.opened_at,
            }
        )
        if result.dropped:
            logger.info("drop %s: %s", trader.trader_id, result.drop_reason)
            return None
        return result.signal
