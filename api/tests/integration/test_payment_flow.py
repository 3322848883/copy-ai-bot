# 支付全链路集成测试（Task 13：提交 tx → 即时确认 → 激活订阅）
# 使用内存 SQLite + 可控 fake chain client（不触真实 RPC）
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.core.security import hash_password


class FakeClient:
    """可控确认数的假链客户端。"""

    def __init__(self, exists=True, confirmations=None, validate_ok=True):
        self._exists = exists
        self._confirmations = confirmations
        self._validate_ok = validate_ok

    async def get_confirmations(self, tx_hash):
        return self._exists, self._confirmations or 0, {}

    async def validate_tx(self, tx_hash, expected_to, expected_value_usdt):
        return self._validate_ok, ""


@pytest.fixture
async def db_env():
    from api.db.base import Base
    from api.models import PlatformAddress, User  # noqa: F401 触发模型注册

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        db.add(User(id=1, email="buyer@test.com", password_hash=hash_password("x" * 8), is_active=True, role="user"))
        db.add(PlatformAddress(network="trc20", address="TQmqKjv7wv9kYp5qU2N5Jh8Z3sL7hX5wJw", status="active"))
        await db.commit()
    return engine, Session


class TestPaymentFlow:
    async def test_submit_tx_immediate_confirm(self, db_env, monkeypatch):
        engine, Session = db_env
        from sqlalchemy import select

        from api.models.billing import Subscription
        from api.services.payment.service import PaymentService

        import api.services.payment.service as payment_mod

        monkeypatch.setattr(payment_mod, "get_chain_client", lambda network: FakeClient(confirmations=99))

        async with Session() as db:
            svc = PaymentService(db)
            order = await svc.create_order(user_id=1, plan_id="trial_5u", network="trc20")
            updated = await svc.submit_tx(order.id, 1, "mock_confirm_abc")
            assert updated.status == "confirmed"
            sub = await db.scalar(
                select(Subscription).where(Subscription.user_id == 1, Subscription.status == "active")
            )
            assert sub is not None
            assert sub.plan_id == "trial_5u"
        await engine.dispose()

    async def test_submit_tx_below_threshold_verifying(self, db_env, monkeypatch):
        engine, Session = db_env
        from api.models.billing import PaymentOrder
        from api.services.payment.service import PaymentService

        import api.services.payment.service as payment_mod

        monkeypatch.setattr(payment_mod, "get_chain_client", lambda network: FakeClient(confirmations=1))

        async with Session() as db:
            svc = PaymentService(db)
            order = await svc.create_order(user_id=1, plan_id="trial_5u", network="trc20")
            updated = await svc.submit_tx(order.id, 1, "mock_slow_abc")
            assert updated.status == "verifying"
            assert updated.confirmations == 1
        await engine.dispose()

    async def test_poll_eventually_confirms(self, db_env, monkeypatch):
        engine, Session = db_env
        from sqlalchemy import select

        from api.models.billing import Subscription
        from api.services.payment.service import PaymentService

        import api.services.payment.service as payment_mod

        client = FakeClient(confirmations=1)
        monkeypatch.setattr(payment_mod, "get_chain_client", lambda network: client)

        async with Session() as db:
            svc = PaymentService(db)
            order = await svc.create_order(user_id=1, plan_id="trial_5u", network="trc20")
            await svc.submit_tx(order.id, 1, "mock_slow_abc")
            assert order.status == "verifying"
            # 链上确认数达标后轮询 → 确认 + 激活订阅
            client._confirmations = 99
            updated = await svc.poll_order(order.id)
            assert updated.status == "confirmed"
            sub = await db.scalar(
                select(Subscription).where(Subscription.user_id == 1, Subscription.status == "active")
            )
            assert sub is not None
        await engine.dispose()
