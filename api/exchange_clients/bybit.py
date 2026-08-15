# bybit 官方客户端（决策 B；M3 T3.0 完善）
from __future__ import annotations

from api.exchange_clients.base import ExchangeAdapter
from api.exchange_clients.mock import MockAdapterMixin


class BybitAdapter(MockAdapterMixin, ExchangeAdapter):
    exchange = "bybit"








