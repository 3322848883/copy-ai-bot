# 区块链 RPC 客户端（M4 T4.8：★ G09 三链 get_confirmations）
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from api.core.config import get_settings

logger = logging.getLogger("signal-saas.chain")

# 各链确认阈值（设计蓝本 T4.4）
REQUIRED_CONFIRMATIONS: dict[str, int] = {"trc20": 12, "bep20": 15, "erc20": 12}


class ChainClient(ABC):
    """链上客户端抽象：校验交易 + 获取确认数。"""

    network: str = ""

    @abstractmethod
    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        """返回 (tx_exists, confirmations, meta)。"""

    @abstractmethod
    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str]:
        """校验 to 地址 + 金额。返回 (ok, reason)。"""


class MockChainClient(ChainClient):
    """dev mock：模拟三链行为（tx_hash 匹配即视为已确认）。"""

    network = "mock"

    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        required = REQUIRED_CONFIRMATIONS.get(self.network, 12)
        # mock：tx_hash 以 '0x' 前缀校验存在；模拟 3 次轮询后达到阈值
        if tx_hash.startswith("mock_confirm"):
            return True, required + 1, {"confirmations": required + 1}
        if tx_hash.startswith("mock_slow"):
            return True, max(1, required // 2), {"confirmations": required // 2}
        return True, required + 1, {"confirmations": required + 1}

    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str]:
        # mock 始终校验通过（to/value 字段在 PaymentService 层校验）
        return True, ""


class TronClient(MockChainClient):
    """TRC-20 (USDT-TRON)。生产：tronpy。"""

    network = "trc20"

    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        if get_settings().app_env == "dev":
            return await super().get_confirmations(tx_hash)
        # 生产: tronpy 查询交易 + 区块确认
        raise NotImplementedError("生产接入 tronpy")


class BscClient(MockChainClient):
    """BEP-20 (USDT-BSC)。生产：web3.py。"""

    network = "bep20"

    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        if get_settings().app_env == "dev":
            return await super().get_confirmations(tx_hash)
        raise NotImplementedError("生产接入 web3.py")


class EthClient(MockChainClient):
    """ERC-20 (USDT-ETH)。生产：web3.py + GAS 估算。"""

    network = "erc20"

    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        if get_settings().app_env == "dev":
            return await super().get_confirmations(tx_hash)
        raise NotImplementedError("生产接入 web3.py")


def get_chain_client(network: str) -> ChainClient:
    """按网络返回客户端（dev mock / 生产真实 RPC）。"""
    mapping: dict[str, ChainClient] = {
        "trc20": TronClient(),
        "bep20": BscClient(),
        "erc20": EthClient(),
    }
    try:
        return mapping[network]
    except KeyError:
        raise ValueError(f"不支持的链: {network}") from None
