# 交易所注册表单元测试（Task 2：白名单 + 生产 fail-fast 防 mock 泄漏）
from __future__ import annotations

import pytest

import api.exchange_clients.registry as reg
from api.exchange_clients.gate import GateAdapter
from api.exchange_clients.okx import OkxAdapter


class FakeSettings:
    app_env = "prod"
    enabled_exchanges = "gate"

    def enabled_exchange_list(self) -> list[str]:
        return [x.strip() for x in self.enabled_exchanges.split(",") if x.strip()]


def _setup(monkeypatch, settings) -> None:
    """重置注册表状态并用指定 settings 重新初始化。"""
    monkeypatch.setattr(reg, "_initialized", False)
    reg.registry._adapters.clear()
    monkeypatch.setattr(reg, "get_settings", lambda: settings)
    reg.init_adapters(force=True)


class TestProdFailFast:
    def test_gate_only_registered(self, monkeypatch):
        _setup(monkeypatch, FakeSettings())
        assert reg.registered_exchanges() == ["gate"]
        assert isinstance(reg.get_adapter("gate"), GateAdapter)
        assert reg.is_mock("gate") is False

    def test_mock_in_whitelist_skipped(self, monkeypatch):
        # prod 白名单含 okx（mock）→ 拒绝注册，仅 gate 生效
        s = FakeSettings()
        s.enabled_exchanges = "gate,okx"
        _setup(monkeypatch, s)
        assert reg.registered_exchanges() == ["gate"]

    def test_mock_only_whitelist_nothing_registered(self, monkeypatch):
        s = FakeSettings()
        s.enabled_exchanges = "okx"
        _setup(monkeypatch, s)
        assert reg.registered_exchanges() == []

    def test_get_unregistered_raises(self, monkeypatch):
        _setup(monkeypatch, FakeSettings())
        with pytest.raises(ValueError):
            reg.get_adapter("okx")

    def test_is_mock_false_for_unregistered(self, monkeypatch):
        _setup(monkeypatch, FakeSettings())
        assert reg.is_mock("okx") is False


class TestDevRegistersAll:
    def test_dev_all_five(self, monkeypatch):
        s = FakeSettings()
        s.app_env = "dev"
        s.enabled_exchanges = "gate,binance,okx,bybit,bitget"
        _setup(monkeypatch, s)
        names = reg.registered_exchanges()
        assert sorted(names) == ["binance", "bitget", "bybit", "gate", "okx"]
        assert reg.is_mock("okx") is True
        assert reg.is_mock("gate") is False

    def test_dev_mock_ok(self, monkeypatch):
        s = FakeSettings()
        s.app_env = "dev"
        s.enabled_exchanges = "okx"
        _setup(monkeypatch, s)
        assert isinstance(reg.get_adapter("okx"), OkxAdapter)
        assert reg.is_mock("okx") is True


class TestWhitelistParsing:
    def test_empty_string(self, monkeypatch):
        s = FakeSettings()
        s.enabled_exchanges = ""
        _setup(monkeypatch, s)
        assert reg.registered_exchanges() == []

    def test_spaces_tolerated(self):
        s = FakeSettings()
        s.enabled_exchanges = " gate , okx "
        assert s.enabled_exchange_list() == ["gate", "okx"]
