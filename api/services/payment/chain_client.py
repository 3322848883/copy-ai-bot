# 区块链 RPC 客户端（M4 T4.8：★ G09 三链 get_confirmations；生产真实 RPC）
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from api.core.config import get_settings

logger = logging.getLogger("signal-saas.chain")

# 各链确认阈值（设计蓝本 T4.4；ERC-20 提升至 32 对齐行业标准）
REQUIRED_CONFIRMATIONS: dict[str, int] = {"trc20": 12, "bep20": 15, "erc20": 32}

# USDT 合约地址（TRC-20 / BEP-20 / ERC-20）
USDT_CONTRACT: dict[str, str] = {
    "trc20": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "bep20": "0x55d398326f99059fF775485246999027B3197955",
    "erc20": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
}

# ERC-20 ABI（仅 decimals + Transfer 事件）
_ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]

_RPC_TIMEOUT = 10  # 秒


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
        # ★ 修复：mock 固定返回 999（任何链 required ≤32 都立即达标）；
        #   此前按自身 network="mock" 查阈值=12，导致 bep20(15)/erc20(32) 订单永不确认
        if tx_hash.startswith("mock_confirm"):
            return True, 999, {"confirmations": 999}
        if tx_hash.startswith("mock_slow"):
            return True, 1, {"confirmations": 1}
        return True, 999, {"confirmations": 999}

    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str]:
        # mock 始终校验通过（to/value 字段在 PaymentService 层校验）
        return True, ""


class TronClient(ChainClient):
    """TRC-20 (USDT-TRON)。生产：tronpy。"""

    network = "trc20"

    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        """返回 (tx_exists, confirmations, meta)。

        meta["error"] 三态语义（供上层区分"可继续轮询"与"判死"）：
        - "unconfirmed"  : 交易已广播但未上链（继续轮询）
        - "network_error": RPC 故障/超时（继续轮询）
        - "failed"       : 链上回执明确失败（reverted/failed_receipt，判死）
        """
        if get_settings().app_env == "dev":
            return await MockChainClient().get_confirmations(tx_hash)
        try:
            from tronpy import Tron
            from tronpy.providers import HTTPProvider

            client = Tron(provider=HTTPProvider(get_settings().tron_rpc_url, timeout=_RPC_TIMEOUT))
            info = client.get_transaction_info(tx_hash)
            if not info or "blockNumber" not in info:  # 未打包上链
                return False, 0, {"error": "unconfirmed"}
            if info.get("receipt", {}).get("result") != "SUCCESS":
                return False, 0, {"error": "failed"}
            current = client.get_now_block()["block_header"]["raw_data"]["number"]
            confirmations = current - info["blockNumber"] + 1
            return True, confirmations, {}
        except Exception as exc:  # noqa: BLE001 RPC 故障降级：继续轮询而非判死
            logger.warning("tron get_confirmations failed: %s", exc)
            return False, 0, {"error": "network_error", "detail": str(exc)}

    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str]:
        if get_settings().app_env == "dev":
            return True, ""
        try:
            import httpx

            params = {
                "contract_address": USDT_CONTRACT["trc20"],
                "transaction_id": tx_hash,
            }
            async with httpx.AsyncClient(timeout=_RPC_TIMEOUT) as c:
                resp = await c.get("https://apilist.tronscanapi.com/api/token_trc20/transfers", params=params)
                resp.raise_for_status()
            data = resp.json()
            transfers = data.get("token_transfers") or data.get("data") or []
            if not transfers:
                return False, "no trc20 transfer found"
            t = transfers[0]
            to_addr = t.get("to_address") or t.get("to")
            raw_amount = t.get("quant") or t.get("amount_str") or t.get("amount")
            amount = float(raw_amount) / 10**6 if not str(raw_amount).isdigit() or "." in str(raw_amount) else float(raw_amount) / 10**6
            if str(to_addr).lower() != str(expected_to).lower():
                return False, "to address mismatch"
            if amount < expected_value_usdt:
                return False, "value insufficient"
            return True, ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("tron validate_tx failed: %s", exc)
            return False, str(exc)


class EvmClient(ChainClient):
    """EVM 链（BEP-20 / ERC-20）共享实现：web3.py。"""

    network = ""

    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        """错误三态语义同 TronClient（unconfirmed / network_error / failed）。"""
        if get_settings().app_env == "dev":
            return await MockChainClient().get_confirmations(tx_hash)
        try:
            from web3 import Web3

            rpc_url = get_settings().bsc_rpc_url if self.network == "bep20" else get_settings().eth_rpc_url
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": _RPC_TIMEOUT}))
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt is None:  # 未打包
                return False, 0, {"error": "unconfirmed"}
            if receipt["status"] != 1:
                return False, 0, {"error": "failed"}
            latest = w3.eth.get_block("latest")["number"]
            confirmations = latest - receipt["blockNumber"] + 1
            return True, confirmations, {}
        except Exception as exc:  # noqa: BLE001 RPC 故障：继续轮询而非判死
            logger.warning("%s get_confirmations failed: %s", self.network, exc)
            return False, 0, {"error": "network_error", "detail": str(exc)}

    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str]:
        if get_settings().app_env == "dev":
            return True, ""
        try:
            from web3 import Web3

            rpc_url = get_settings().bsc_rpc_url if self.network == "bep20" else get_settings().eth_rpc_url
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": _RPC_TIMEOUT}))
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt is None or receipt["status"] != 1:
                return False, "tx not confirmed"
            contract = w3.eth.contract(address=Web3.to_checksum_address(USDT_CONTRACT[self.network]), abi=_ERC20_ABI)
            events = contract.events.Transfer().process_receipt(receipt)
            if not events:
                return False, "no usdt transfer event"
            args = events[0]["args"]
            to_addr = args["to"]
            amount = args["value"] / 10**6
            if str(to_addr).lower() != str(expected_to).lower():
                return False, "to address mismatch"
            if amount < expected_value_usdt:
                return False, "value insufficient"
            return True, ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s validate_tx failed: %s", self.network, exc)
            return False, str(exc)


class BscClient(EvmClient):
    """BEP-20 (USDT-BSC)。"""

    network = "bep20"


class EthClient(EvmClient):
    """ERC-20 (USDT-ETH)。"""

    network = "erc20"


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
