# 区块链 RPC 客户端（M4 T4.8：★ G09 三链 get_confirmations；生产真实 RPC）
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from api.core.config import get_settings

logger = logging.getLogger("signal-saas.chain")

# 各链确认阈值（设计蓝本 T4.4；ERC-20 提升至 32 对齐行业标准）
REQUIRED_CONFIRMATIONS: dict[str, int] = {"trc20": 12, "bep20": 15, "erc20": 32, "aptos": 20}

# USDT 合约地址（TRC-20 / BEP-20 / ERC-20 / APTOS 资产类型）
USDT_CONTRACT: dict[str, str] = {
    "trc20": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "bep20": "0x55d398326f99059fF775485246999027B3197955",
    "erc20": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "aptos": "0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDT",
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

# USDT 各链小数位（★ H5：BSC-USDT 是 18 位，与 ETH 的 6 位不同，写错金额放大 10^12 倍）
USDT_DECIMALS = {"trc20": 6, "bep20": 18, "erc20": 6, "aptos": 6}

# EVM 公共 RPC 备用节点（主节点在 settings.bsc_rpc_url / eth_rpc_url；主节点限流时依次回退）
_RPC_FALLBACKS = {
    "bep20": ["https://bsc.meowrpc.com", "https://bsc.blockrazor.xyz", "https://1rpc.io/bnb"],
    "erc20": ["https://eth.merkle.io", "https://1rpc.io/eth", "https://rpc.ankr.com/eth"],
}



class ChainClient(ABC):
    """链上客户端抽象：校验交易 + 获取确认数。"""

    network: str = ""

    @abstractmethod
    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        """返回 (tx_exists, confirmations, meta)。"""

    @abstractmethod
    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str, float | None]:
        """校验 to 地址 + 金额。返回 (ok, reason, 实际到账USDT)。"""

    @abstractmethod
    async def get_tx_timestamp(self, tx_hash: str) -> int | None:
        """交易上链时间（unix 秒）；未知返回 None（上层跳过时间窗校验）。"""


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

    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str, float | None]:
        # mock 始终校验通过（to/value 字段在 PaymentService 层校验）；金额按订单值模拟
        return True, "", expected_value_usdt

    async def get_tx_timestamp(self, tx_hash: str) -> int | None:
        import time

        return int(time.time())


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

    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str, float | None]:
        if get_settings().app_env == "dev":
            return True, "", expected_value_usdt
        try:
            import httpx

            # ★ H5：交易所批量提现一笔交易可含几十上百条 USDT 腿，接口按页分页
            #   （limit 上限 50，实测 100/200 直接 400），平台收款腿可能不在第一页 → 翻页遍历
            matched_amount: float | None = None
            start = 0
            async with httpx.AsyncClient(timeout=_RPC_TIMEOUT) as c:
                while True:
                    resp = await c.get(
                        "https://apilist.tronscanapi.com/api/token_trc20/transfers",
                        params={
                            "contract_address": USDT_CONTRACT["trc20"],
                            "transaction_id": tx_hash,
                            "start": start,
                            "limit": 50,
                        },
                    )
                    resp.raise_for_status()
                    transfers = resp.json().get("token_transfers") or []
                    if not transfers:
                        break
                    for t in transfers:
                        to_addr = t.get("to_address") or t.get("to")
                        raw_amount = t.get("quant") or t.get("amount_str") or t.get("amount")
                        amount = float(raw_amount) / 10**6
                        if str(to_addr).lower() != str(expected_to).lower():
                            continue
                        matched_amount = amount if matched_amount is None else max(matched_amount, amount)
                        if amount >= expected_value_usdt:
                            return True, "", amount
                    if len(transfers) < 50:
                        break
                    start += 50
                    if start >= 2000:
                        break
            if matched_amount is not None:
                return False, "value insufficient", matched_amount
            return False, "no trc20 transfer to target", None
        except Exception as exc:  # noqa: BLE001
            logger.warning("tron validate_tx failed: %s", exc)
            return False, str(exc), None

    async def get_tx_timestamp(self, tx_hash: str) -> int | None:
        """tronscanapi transaction-info 的 timestamp（毫秒）→ unix 秒。

        ★ H5：字段名是 timestamp（blockTimestamp 实测不存在）；
        trongrid 免费档限流（实测返回空 data）导致时间窗校验被静默跳过。
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_RPC_TIMEOUT) as c:
                r = await c.get("https://apilist.tronscanapi.com/api/transaction-info", params={"hash": tx_hash})
                r.raise_for_status()
            ts_ms = r.json().get("timestamp")
            return int(ts_ms) // 1000 if ts_ms else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("tron get_tx_timestamp failed: %s", exc)
            return None


class EvmClient(ChainClient):
    """EVM 链（BEP-20 / ERC-20）共享实现：web3.py。

    ★ H5 修复（2026-08-19 三链零成本验证发现）：
    - BSC-USDT 是 **18 位小数**（ETH-USDT 是 6 位），旧代码硬编码 /10**6 → 金额放大
      10^12 倍，真实转 0.000001 USDT 即可过任意订单校验（严重漏洞），按链查 USDT_DECIMALS；
    - 旧代码只看 receipts 的**第一笔** Transfer 事件，多腿交易（路由/批量提现）会误拒，
      现遍历全部事件匹配 (to, amount)；
    - 公共 RPC 会限流（bsc.publicnode.com 实测 403），主节点 + 备用节点依次回退。
    """

    network = ""

    def _w3_list(self):
        """主节点（settings）+ 备用节点，供失败回退。

        BSC 是 POA 链，区块 extraData 超 32 字节，web3 必须注入 POA 中间件
        否则 eth_getBlock 直接抛异常（get_confirmations 的确认数计算依赖 get_block）。
        """
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        rpc = get_settings().bsc_rpc_url if self.network == "bep20" else get_settings().eth_rpc_url
        urls = [rpc, *_RPC_FALLBACKS.get(self.network, [])]
        conns = []
        for u in urls:
            w3 = Web3(Web3.HTTPProvider(u, request_kwargs={"timeout": _RPC_TIMEOUT}))
            if self.network == "bep20":
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            conns.append(w3)
        return conns

    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        """错误三态语义同 TronClient（unconfirmed / network_error / failed）。"""
        if get_settings().app_env == "dev":
            return await MockChainClient().get_confirmations(tx_hash)
        last_exc: Exception | None = None
        for w3 in self._w3_list():
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt is None:  # 未打包
                    return False, 0, {"error": "unconfirmed"}
                if receipt["status"] != 1:
                    return False, 0, {"error": "failed"}
                latest = w3.eth.get_block("latest")["number"]
                confirmations = latest - receipt["blockNumber"] + 1
                return True, confirmations, {}
            except Exception as exc:  # noqa: BLE001 单节点故障 → 下一节点
                last_exc = exc
                continue
        logger.warning("%s get_confirmations all rpc failed: %s", self.network, last_exc)
        return False, 0, {"error": "network_error", "detail": str(last_exc)}

    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str, float | None]:
        if get_settings().app_env == "dev":
            return True, "", expected_value_usdt
        from web3 import Web3

        last_exc: Exception | None = None
        for w3 in self._w3_list():
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt is None or receipt["status"] != 1:
                    return False, "tx not confirmed", None
                contract = w3.eth.contract(address=Web3.to_checksum_address(USDT_CONTRACT[self.network]), abi=_ERC20_ABI)
                events = contract.events.Transfer().process_receipt(receipt)
                decimals = USDT_DECIMALS[self.network]
                matched_amount: float | None = None
                for ev in events:
                    args = ev["args"]
                    if str(args["to"]).lower() != str(expected_to).lower():
                        continue
                    amount = args["value"] / 10**decimals
                    matched_amount = amount if matched_amount is None else max(matched_amount, amount)
                    if amount >= expected_value_usdt:
                        return True, "", amount
                if matched_amount is not None:
                    return False, "value insufficient", matched_amount
                return False, "no usdt transfer event to target", None
            except Exception as exc:  # noqa: BLE001 单节点故障 → 下一节点
                last_exc = exc
                continue
        logger.warning("%s validate_tx all rpc failed: %s", self.network, last_exc)
        return False, str(last_exc), None

    async def get_tx_timestamp(self, tx_hash: str) -> int | None:
        """回执所在区块的 timestamp（unix 秒）；多节点回退。"""
        for w3 in self._w3_list():
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt is None:
                    continue
                block = w3.eth.get_block(receipt["blockNumber"])
                return int(block["timestamp"])
            except Exception as exc:  # noqa: BLE001 单节点故障 → 下一节点
                logger.warning("%s get_tx_timestamp rpc failed: %s", self.network, exc)
                continue
        return None


class BscClient(EvmClient):
    """BEP-20 (USDT-BSC)。"""

    network = "bep20"


class EthClient(EvmClient):
    """ERC-20 (USDT-ETH)。"""

    network = "erc20"


class AptosClient(ChainClient):
    """APTOS 网络 USDT。生产：Aptos fullnode REST API（无 EVM 概念，
    交易 version 即链上序号，用 ledger_version 计算确认数）。

    USDT 桥接资产入账有两种事件形态，validate_tx 均支持：
    - 旧 Coin 标准：`0x1::coin::DepositEvent<USDT>`，事件 guid.account_address 即收款方；
    - 新 FungibleAsset 标准（Petra 等钱包 `primary_fungible_store::transfer` 默认路径，
      真金实测 2026-08-18）：`0x1::fungible_asset::Deposit`，data.store 是收款方的
      FungibleStore 对象地址——须经 ObjectCore 反查 owner、FungibleStore.metadata 反查
      symbol 才能确认收款方与资产，不能直接比对账户地址。
    """

    network = "aptos"

    async def _get_tx(self, tx_hash: str) -> dict:
        import httpx

        url = f"{get_settings().aptos_rpc_url}/transactions/by_hash/{tx_hash}"
        async with httpx.AsyncClient(timeout=_RPC_TIMEOUT) as c:
            r = await c.get(url)
            r.raise_for_status()
        return r.json()

    async def _get_resource(self, address: str, resource_type: str) -> dict | None:
        """读任意账户/对象地址下的 resource；404 返回 None（对象不存在等）。"""
        import httpx

        url = f"{get_settings().aptos_rpc_url}/accounts/{address}/resource/{resource_type}"
        async with httpx.AsyncClient(timeout=_RPC_TIMEOUT) as c:
            r = await c.get(url)
            if r.status_code == 404:
                return None
            r.raise_for_status()
        return r.json().get("data") or {}

    async def _fa_store_owner_and_metadata(self, store: str) -> tuple[str, str]:
        """FungibleStore 对象 → (owner 账户, metadata 对象地址)。"""
        core = await self._get_resource(store, "0x1::object::ObjectCore")
        owner = str(core.get("owner") or "")
        fs = await self._get_resource(store, "0x1::fungible_asset::FungibleStore")
        meta_raw = fs.get("metadata") or {}
        meta = meta_raw.get("inner") if isinstance(meta_raw, dict) else str(meta_raw or "")
        return owner, str(meta or "")

    async def _get_ledger_version(self) -> int:
        import httpx

        url = get_settings().aptos_rpc_url.rstrip("/") + "/"
        async with httpx.AsyncClient(timeout=_RPC_TIMEOUT) as c:
            r = await c.get(url)
            r.raise_for_status()
        return int(r.json().get("ledger_version") or 0)

    async def get_confirmations(self, tx_hash: str) -> tuple[bool, int, dict]:
        """错误三态语义同 TronClient（unconfirmed / network_error / failed）。"""
        if get_settings().app_env == "dev":
            return await MockChainClient().get_confirmations(tx_hash)
        try:
            import httpx

            tx = await self._get_tx(tx_hash)
            if tx.get("type") == "pending_transaction" or tx.get("version") is None:  # 未上链
                return False, 0, {"error": "unconfirmed"}
            if tx.get("success") is False:
                return False, 0, {"error": "failed"}
            version = int(tx["version"])
            ledger = await self._get_ledger_version()
            confirmations = max(ledger - version + 1, 0)
            return True, confirmations, {}
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:  # 交易不存在 → 未上链，继续轮询
                return False, 0, {"error": "unconfirmed"}
            logger.warning("aptos get_confirmations http error: %s", exc)
            return False, 0, {"error": "network_error", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.warning("aptos get_confirmations failed: %s", exc)
            return False, 0, {"error": "network_error", "detail": str(exc)}

    async def validate_tx(self, tx_hash: str, expected_to: str, expected_value_usdt: float) -> tuple[bool, str, float | None]:
        if get_settings().app_env == "dev":
            return True, "", expected_value_usdt
        try:
            tx = await self._get_tx(tx_hash)
            if tx.get("success") is not True:
                return False, "tx not success", None
            usdt = get_settings().aptos_usdt
            coin_module = usdt.split("::")[0]  # 资产合约地址段，用于过滤是否是 USDT 类事件
            for ev in tx.get("events") or []:
                etype = ev.get("type") or ""
                data = ev.get("data") or {}
                if "coin::DepositEvent" in etype and coin_module in etype:
                    # 旧 Coin 标准：guid.account_address 即收款方
                    recv = (ev.get("guid") or {}).get("account_address") or ""
                    amount = int(data.get("amount") or 0)
                    val_usdt = amount / 10**6
                    if str(recv).lower() == str(expected_to).lower() and val_usdt >= expected_value_usdt:
                        return True, "", val_usdt
                elif etype.endswith("fungible_asset::Deposit"):
                    # 新 FA 标准：store 反查 owner + metadata symbol 双重确认
                    amount = int(data.get("amount") or 0)
                    val_usdt = amount / 10**6
                    if val_usdt < expected_value_usdt:
                        continue
                    store = data.get("store") or ""
                    if not store:
                        continue
                    owner, meta_obj = await self._fa_store_owner_and_metadata(store)
                    if owner.lower() != str(expected_to).lower() or not meta_obj:
                        continue
                    meta = await self._get_resource(meta_obj, "0x1::fungible_asset::Metadata")
                    if str(meta.get("symbol") or "").upper() != "USDT":
                        continue
                    return True, "", val_usdt
            return False, "no usdt deposit event to target", None
        except Exception as exc:  # noqa: BLE001
            logger.warning("aptos validate_tx failed: %s", exc)
            return False, str(exc), None

    async def get_tx_timestamp(self, tx_hash: str) -> int | None:
        """tx.timestamp（微秒字符串）→ unix 秒。"""
        try:
            tx = await self._get_tx(tx_hash)
            ts_us = tx.get("timestamp")
            return int(ts_us) // 1_000_000 if ts_us else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("aptos get_tx_timestamp failed: %s", exc)
            return None


def get_chain_client(network: str) -> ChainClient:
    """按网络返回客户端（dev mock / 生产真实 RPC）。"""
    mapping: dict[str, ChainClient] = {
        "trc20": TronClient(),
        "bep20": BscClient(),
        "erc20": EthClient(),
        "aptos": AptosClient(),
    }
    try:
        return mapping[network]
    except KeyError:
        raise ValueError(f"不支持的链: {network}") from None
