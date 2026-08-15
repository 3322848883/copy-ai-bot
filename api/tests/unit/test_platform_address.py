# 平台收款地址单元测试（Task 1.5）
# 覆盖：地址格式校验 / TxHash 格式校验 / 模型注册 / active 地址读取
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routers.admin.payments import _validate_address
from api.services.payment.service import PaymentService


class TestAddressFormat:
    def test_trc20_valid(self):
        _validate_address("trc20", "TQmqKjv7wv9kYp5qU2N5Jh8Z3sL7hX5wJw")  # 不抛异常

    @pytest.mark.parametrize("bad", ["0x1111111111111111111111111111111111111111", "Tshort", "abc", ""])
    def test_trc20_invalid(self, bad):
        with pytest.raises(Exception):
            _validate_address("trc20", bad)

    def test_evm_valid(self):
        _validate_address("bep20", "0x1111111111111111111111111111111111111111")
        _validate_address("erc20", "0x2222222222222222222222222222222222222222")

    @pytest.mark.parametrize("bad", ["TQmqKjv7wv9kYp5qU2N5Jh8Z3sL7hX5wJw", "0x123", "0x" + "1" * 41, ""])
    def test_evm_invalid(self, bad):
        with pytest.raises(Exception):
            _validate_address("bep20", bad)

    def test_unknown_network(self):
        with pytest.raises(Exception):
            _validate_address("btc", "anything")


class TestTxHashFormat:
    def test_tron_valid(self):
        assert PaymentService._valid_tx_format("trc20", "a" * 64) is True

    def test_tron_invalid(self):
        assert PaymentService._valid_tx_format("trc20", "0x" + "a" * 64) is False
        assert PaymentService._valid_tx_format("trc20", "short") is False

    def test_evm_valid(self):
        assert PaymentService._valid_tx_format("erc20", "0x" + "a" * 64) is True
        assert PaymentService._valid_tx_format("bep20", "0x" + "A" * 64) is True

    def test_evm_invalid(self):
        assert PaymentService._valid_tx_format("erc20", "a" * 64) is False
        assert PaymentService._valid_tx_format("erc20", "0x" + "a" * 63) is False


class TestModelRegistered:
    def test_platform_address_table_exists(self):
        from api.db.base import Base
        from api.models import PlatformAddress  # noqa: F401 触发模型注册

        names = {t.name for t in Base.metadata.sorted_tables}
        assert "platform_addresses" in names


class TestActiveAddressQuery:
    """内存 SQLite 验证 _verify_to 读取该链最新 active 地址。"""

    async def test_read_latest_active(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        from api.db.base import Base
        from api.models import PlatformAddress, PaymentOrder

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)


        async with Session() as db:
            db.add(PlatformAddress(network="trc20", address="TOld", status="inactive"))
            db.add(PlatformAddress(network="trc20", address="TNew", status="active"))
            order = PaymentOrder(user_id=1, plan_id="trial_5u", amount_usdt=5.0, network="trc20", status="pending")
            db.add(order)
            await db.commit()
            svc = PaymentService(db)
            ok, reason = await svc._verify_to(order)
            assert ok is True
            assert svc._platform_address == "TNew"

        await engine.dispose()

    async def test_no_active_returns_reason(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        from api.db.base import Base
        from api.models import PaymentOrder

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        async with Session() as db:
            order = PaymentOrder(user_id=1, plan_id="trial_5u", amount_usdt=5.0, network="bep20", status="pending")
            db.add(order)
            await db.commit()
            svc = PaymentService(db)
            ok, reason = await svc._verify_to(order)
            assert ok is False
            assert "bep20" in reason and "未配置" in reason

        await engine.dispose()
