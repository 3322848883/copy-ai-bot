"""5 家交易所客户端注册表（决策 B：官方直连；V1 生产白名单 + fail-fast）。"""
from __future__ import annotations

import logging

from api.core.config import get_settings
from api.exchange_clients.base import ExchangeAdapter

logger = logging.getLogger("signal-saas.exchange.registry")


class AdapterRegistry:
    """按交易所名注册/获取官方适配器。"""

    def __init__(self) -> None:
        self._adapters: dict[str, ExchangeAdapter] = {}

    def register(self, adapter: ExchangeAdapter) -> None:
        self._adapters[adapter.exchange] = adapter

    def get(self, exchange: str) -> ExchangeAdapter:
        try:
            return self._adapters[exchange]
        except KeyError:
            raise ValueError(f"exchange adapter not registered: {exchange}") from None

    def all(self) -> list[ExchangeAdapter]:
        return list(self._adapters.values())

    def names(self) -> list[str]:
        return list(self._adapters.keys())


registry = AdapterRegistry()
_initialized = False


def init_adapters(force: bool = False) -> None:
    """启动时按白名单注册适配器（生产拒绝 mock 适配器，防假成交）。

    - FastAPI startup 与 Celery worker 进程均可调用
    - 幂等：已初始化则跳过（force=True 强制重建）
    - 生产 fail-fast：app_env != dev 时，白名单内若是 MockAdapterMixin 实例则拒绝注册并 critical 告警
    """
    global _initialized
    if _initialized and not force:
        return
    from api.exchange_clients.binance import BinanceAdapter
    from api.exchange_clients.bitget import BitgetAdapter
    from api.exchange_clients.bybit import BybitAdapter
    from api.exchange_clients.gate import GateAdapter
    from api.exchange_clients.mock import MockAdapterMixin
    from api.exchange_clients.okx import OkxAdapter

    settings = get_settings()
    enabled = set(settings.enabled_exchange_list())
    candidates = [GateAdapter(), BinanceAdapter(), OkxAdapter(), BybitAdapter(), BitgetAdapter()]
    for adapter in candidates:
        if adapter.exchange not in enabled:
            logger.info("exchange %s not enabled, skip", adapter.exchange)
            continue
        if settings.app_env != "dev" and isinstance(adapter, MockAdapterMixin):
            # 生产禁止注册 mock 适配器：防止静默假成交
            logger.critical(
                "exchange %s is MOCK but app_env=%s — refusing to register",
                adapter.exchange, settings.app_env,
            )
            continue
        registry.register(adapter)
    _initialized = True


def get_adapter(exchange: str) -> ExchangeAdapter:
    """惰性获取适配器：确保已初始化（供 Celery worker 等非 FastAPI 进程使用）。"""
    if not _initialized:
        init_adapters()
    return registry.get(exchange)


def registered_exchanges() -> list[str]:
    """当前已注册交易所（后台状态展示 / 启动日志）。"""
    if not _initialized:
        init_adapters()
    return registry.names()


def is_mock(exchange: str) -> bool:
    """指定交易所是否为 mock 适配器。"""
    from api.exchange_clients.mock import MockAdapterMixin

    try:
        adapter = get_adapter(exchange)
    except ValueError:
        return False
    return isinstance(adapter, MockAdapterMixin)
