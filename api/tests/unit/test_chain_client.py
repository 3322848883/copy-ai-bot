# 链上支付客户端单元测试（Task 1：三链 RPC 真实接入）
# 覆盖：mock 行为 / TRON 确认数计算 / EVM 确认数计算 / 失败回滚 / 异常降级 / validate_tx 校验
from __future__ import annotations

import sys
import types

import pytest

from api.services.payment.chain_client import (
    MockChainClient,
    REQUIRED_CONFIRMATIONS,
    TronClient,
    BscClient,
    EthClient,
    get_chain_client,
)


class FakeSettings:
    app_env = "prod"
    tron_rpc_url = "https://tron.test"
    bsc_rpc_url = "https://bsc.test"
    eth_rpc_url = "https://eth.test"


@pytest.fixture
def prod_env(monkeypatch):
    import api.services.payment.chain_client as cc

    monkeypatch.setattr(cc, "get_settings", lambda: FakeSettings())
    return cc


def _install_fake_tronpy(monkeypatch, info=None, now_block=None, raise_exc: Exception | None = None):
    """安装假 tronpy 模块（生产分支 import 路径）。"""
    mod = types.ModuleType("tronpy")
    providers = types.ModuleType("tronpy.providers")

    class HTTPProvider:
        def __init__(self, url, timeout=None):
            self.url = url

    class Tron:
        def __init__(self, provider=None):
            pass

        def get_transaction_info(self, tx_hash):
            if raise_exc is not None:
                raise raise_exc
            return info

        def get_now_block(self):
            return now_block

    providers.HTTPProvider = HTTPProvider
    mod.providers = providers
    mod.Tron = Tron
    monkeypatch.setitem(sys.modules, "tronpy", mod)
    monkeypatch.setitem(sys.modules, "tronpy.providers", providers)


def _install_fake_web3(monkeypatch, receipt=None, latest=100, transfer_events=None, raise_exc: Exception | None = None):
    """安装假 web3 模块（生产分支 import 路径）。"""
    mod = types.ModuleType("web3")
    middleware = types.ModuleType("web3.middleware")
    middleware.ExtraDataToPOAMiddleware = object()

    class HTTPProvider:
        def __init__(self, url, request_kwargs=None):
            self.url = url

    class TransferEvent:
        def process_receipt(self, receipt):
            return transfer_events or []

    class Events:
        Transfer = TransferEvent

    class Contract:
        events = Events()

    class Eth:
        def get_transaction_receipt(self, tx_hash):
            if raise_exc is not None:
                raise raise_exc
            return receipt

        def get_block(self, tag):
            return {"number": latest}

        def contract(self, address, abi):
            return Contract()

    class Web3Class:
        def __init__(self, provider=None):
            self.eth = Eth()
            self.middleware_onion = types.SimpleNamespace(inject=lambda *args, **kwargs: None)

        @staticmethod
        def to_checksum_address(addr):
            return addr

        @staticmethod
        def HTTPProvider(url, request_kwargs=None):
            return HTTPProvider(url, request_kwargs)

    mod.Web3 = Web3Class
    monkeypatch.setitem(sys.modules, "web3", mod)
    monkeypatch.setitem(sys.modules, "web3.middleware", middleware)


# ── mock 行为 ──
class TestMockChainClient:
    async def test_confirm_hash_reaches_threshold(self):
        client = MockChainClient()
        ok, conf, meta = await client.get_confirmations("mock_confirm_abc")
        assert ok is True
        assert conf == 999  # mock 固定 999，任何链阈值均满足

    async def test_slow_hash_below_threshold(self):
        client = MockChainClient()
        ok, conf, _ = await client.get_confirmations("mock_slow_abc")
        assert ok is True
        assert conf < REQUIRED_CONFIRMATIONS["trc20"]

    async def test_validate_always_pass(self):
        client = MockChainClient()
        ok, reason, actual = await client.validate_tx("mock_confirm_abc", "Txxx", 5.0)
        assert ok is True
        assert reason == ""
        assert actual == 5.0


# ── TRON 生产分支 ──
class TestTronClient:
    async def test_confirmations_calc(self, prod_env, monkeypatch):
        _install_fake_tronpy(
            monkeypatch,
            info={"blockNumber": 90, "receipt": {"result": "SUCCESS"}},
            now_block={"block_header": {"raw_data": {"number": 100}}},
        )
        ok, conf, meta = await TronClient().get_confirmations("tx")
        assert ok is True
        assert conf == 11  # 100 - 90 + 1

    async def test_unconfirmed_no_block(self, prod_env, monkeypatch):
        _install_fake_tronpy(monkeypatch, info={"receipt": {"result": "SUCCESS"}})
        ok, conf, meta = await TronClient().get_confirmations("tx")
        assert ok is False
        assert conf == 0

    async def test_failed_receipt(self, prod_env, monkeypatch):
        _install_fake_tronpy(
            monkeypatch,
            info={"blockNumber": 90, "receipt": {"result": "FAILED"}},
            now_block={"block_header": {"raw_data": {"number": 100}}},
        )
        ok, conf, _ = await TronClient().get_confirmations("tx")
        assert ok is False
        assert conf == 0

    async def test_rpc_exception_degrades(self, prod_env, monkeypatch):
        _install_fake_tronpy(monkeypatch, raise_exc=RuntimeError("timeout"))
        ok, conf, meta = await TronClient().get_confirmations("tx")
        assert ok is False
        assert conf == 0
        # ★ 修复语义：RPC 故障标记 network_error（可继续轮询），detail 携带原始错误
        assert meta.get("error") == "network_error"
        assert "timeout" in meta.get("detail", "")

    async def test_dev_uses_mock(self, monkeypatch):
        import api.services.payment.chain_client as cc

        class DevSettings(FakeSettings):
            app_env = "dev"

        monkeypatch.setattr(cc, "get_settings", lambda: DevSettings())
        ok, conf, _ = await TronClient().get_confirmations("mock_confirm_x")
        assert ok is True


# ── EVM 生产分支 ──
class TestEvmClient:
    async def test_bsc_confirmations_calc(self, prod_env, monkeypatch):
        _install_fake_web3(monkeypatch, receipt={"blockNumber": 50, "status": 1}, latest=60)
        ok, conf, _ = await BscClient().get_confirmations("0xabc")
        assert ok is True
        assert conf == 11

    async def test_erc20_confirmations_calc(self, prod_env, monkeypatch):
        _install_fake_web3(monkeypatch, receipt={"blockNumber": 5, "status": 1}, latest=40)
        ok, conf, _ = await EthClient().get_confirmations("0xabc")
        assert ok is True
        assert conf == 36

    async def test_reverted_tx(self, prod_env, monkeypatch):
        _install_fake_web3(monkeypatch, receipt={"blockNumber": 50, "status": 0}, latest=60)
        ok, conf, _ = await BscClient().get_confirmations("0xabc")
        assert ok is False
        assert conf == 0

    async def test_unconfirmed_none_receipt(self, prod_env, monkeypatch):
        _install_fake_web3(monkeypatch, receipt=None)
        ok, conf, _ = await BscClient().get_confirmations("0xabc")
        assert ok is False
        assert conf == 0

    async def test_rpc_exception_degrades(self, prod_env, monkeypatch):
        _install_fake_web3(monkeypatch, raise_exc=RuntimeError("connection refused"))
        ok, conf, meta = await BscClient().get_confirmations("0xabc")
        assert ok is False
        assert conf == 0
        assert meta.get("error") == "network_error"

    async def test_validate_tx_ok(self, prod_env, monkeypatch):
        event = {"args": {"to": "0xPlatform", "value": int(10.0 * 10**18)}}
        _install_fake_web3(monkeypatch, receipt={"blockNumber": 1, "status": 1}, transfer_events=[event])
        ok, reason, actual = await BscClient().validate_tx("0xabc", "0xplatform", 10.0)
        assert ok is True
        assert reason == ""
        assert actual == 10.0

    async def test_validate_tx_to_mismatch(self, prod_env, monkeypatch):
        event = {"args": {"to": "0xOther", "value": int(10.0 * 10**18)}}
        _install_fake_web3(monkeypatch, receipt={"blockNumber": 1, "status": 1}, transfer_events=[event])
        ok, reason, actual = await BscClient().validate_tx("0xabc", "0xplatform", 10.0)
        assert ok is False
        assert "target" in reason
        assert actual is None

    async def test_validate_tx_value_insufficient(self, prod_env, monkeypatch):
        event = {"args": {"to": "0xPlatform", "value": int(5.0 * 10**18)}}
        _install_fake_web3(monkeypatch, receipt={"blockNumber": 1, "status": 1}, transfer_events=[event])
        ok, reason, actual = await BscClient().validate_tx("0xabc", "0xplatform", 10.0)
        assert ok is False
        assert "insufficient" in reason
        assert actual == 5.0

    async def test_validate_tx_no_event(self, prod_env, monkeypatch):
        _install_fake_web3(monkeypatch, receipt={"blockNumber": 1, "status": 1}, transfer_events=[])
        ok, reason, actual = await BscClient().validate_tx("0xabc", "0xplatform", 10.0)
        assert ok is False
        assert "no usdt transfer" in reason
        assert actual is None


# ── 工厂 ──
class TestGetChainClient:
    def test_returns_by_network(self):
        assert isinstance(get_chain_client("trc20"), TronClient)
        assert isinstance(get_chain_client("bep20"), BscClient)
        assert isinstance(get_chain_client("erc20"), EthClient)

    def test_unknown_network_raises(self):
        with pytest.raises(ValueError):
            get_chain_client("btc")
