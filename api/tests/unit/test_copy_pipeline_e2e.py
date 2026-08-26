"""采集后半链端到端：信号匹配 -> 订阅/风控 -> 模拟成交 -> 订单/仓位 -> WS 事件。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import MethodType

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import api.models  # noqa: F401 注册全部 ORM 表
from api.db.base import Base
from api.models.billing import Subscription
from api.models.bot import CopyBot, CopyOrder, PositionSnapshot
from api.models.exchange import ContractSpec
from api.models.signal import SourceSignal, Strategy, Trader
from api.models.user import ApiKey, Identity, User
from api.services.apikeyvault.service import ApiKeyVaultService
from api.services.copyengine.service import CopyEngine


def test_copy_pipeline_persists_fill_position_and_cross_process_events(monkeypatch):
    events: list[tuple[int, str, dict]] = []

    async def fake_publish(user_id: int, channel: str, payload: dict) -> None:
        events.append((user_id, channel, payload))

    async def fake_price(symbol: str) -> float:
        return 100.0

    monkeypatch.setattr("api.ws.broker.publish_user_event", fake_publish)
    monkeypatch.setattr("api.services.prices.fetch_futures_price", fake_price)
    monkeypatch.setattr(
        "api.services.settings.service.risk_rule_float",
        lambda key, default: default,
    )

    async def scenario() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as db:
            user = User(
                email="copy@example.com", password_hash="x", is_active=True,
                risk_disclosure_accepted=True,
            )
            db.add(user)
            await db.flush()
            db.add(Identity(user_id=user.id, identity_type="normal", locked=False))
            db.add(Subscription(
                user_id=user.id, plan_id="monthly", status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            ))
            trader = Trader(exchange="gate", trader_id="32801", name="leader", followers=1)
            db.add(trader)
            await db.flush()
            strategy = Strategy(
                trader_id=trader.id, source_exchange="gate", display_name="leader",
                style="trend", risk_rating="mid", gray_pct=100, status="listed",
                source="B", follow_enabled=True,
            )
            db.add(strategy)
            await db.flush()
            vault = ApiKeyVaultService("0" * 64)
            ciphertext, nonce, tag, aad = vault.encrypt("key\nsecret", f"{user.id}|gate")
            api_key = ApiKey(
                user_id=user.id, exchange="gate", ciphertext=ciphertext,
                nonce=nonce, tag=tag, aad=aad, status="active",
            )
            db.add(api_key)
            await db.flush()
            bot = CopyBot(
                user_id=user.id, strategy_id=strategy.id, exchange="gate",
                api_key_id=api_key.id, amount_mode="fixed", fixed_amount_usdt=100,
                percent=None, leverage=10, margin_mode="isolated",
                max_total_position_usdt=10_000, virtual_locked_usdt=0,
                status="active", paper=True,
            )
            db.add(bot)
            db.add(ContractSpec(
                exchange="gate", symbol="MSTRXUSDT", face_value_usdt=0.01,
                min_size=1, size_precision=0,
            ))
            await db.flush()
            now = datetime.now(timezone.utc)
            signal = SourceSignal(
                exchange="gate", source_trader_id="32801", symbol="MSTRXUSDT",
                side="short", leverage=1, qty=0, percent=None, action="open",
                source_mode="B", opened_at=now, received_at=now,
                dedupe_key="e2e-open", dropped=False,
            )
            db.add(signal)
            await db.commit()

            copy_engine = CopyEngine(db)
            # 单元环境没有 Redis；生产全局风控钩子另有独立检查。
            copy_engine.risk._hooks.clear()
            orders = await copy_engine.handle_signal(signal)
            assert len(orders) == 1
            order = orders[0]
            assert order.status == "filled"
            assert order.filled_qty == order.qty > 0
            assert order.avg_price == 100.0
            assert order.exchange_order_id.startswith("paper-")
            assert order.client_order_id.startswith("t-cp")

            # 同一信号再次投递不得生成第二笔订单或再次执行。
            assert await copy_engine.handle_signal(signal) == []
            same_signal_orders = (
                await db.execute(
                    __import__("sqlalchemy").select(CopyOrder).where(
                        CopyOrder.bot_id == bot.id,
                        CopyOrder.signal_id == signal.id,
                    )
                )
            ).scalars().all()
            assert len(same_signal_orders) == 1

            stored = await db.get(CopyOrder, order.id)
            assert stored is not None and stored.status == "filled"
            position = (
                await db.execute(
                    __import__("sqlalchemy").select(PositionSnapshot).where(
                        PositionSnapshot.bot_id == bot.id,
                        PositionSnapshot.symbol == "MSTRXUSDT",
                        PositionSnapshot.is_open == True,  # noqa: E712
                    )
                )
            ).scalars().one()
            assert position.side == "short"
            assert position.qty == order.filled_qty

            channels = [channel for _, channel, _ in events]
            assert channels == ["signal.new", "bot.order", "bot.position"]
            assert events[1][2]["avg_price"] == 100.0
            assert events[1][2]["exchange_order_id"].startswith("paper-")

            # paused/stopped 机器人不能再被策略匹配。
            bot.status = "paused"
            await db.commit()
            assert await copy_engine.match_bots("gate", "32801") == []
            bot.status = "active"

            # 订阅到期：机器人仍 active，但新开仓必须落失败单并推送明确原因。
            sub = (
                await db.execute(
                    __import__("sqlalchemy").select(Subscription).where(
                        Subscription.user_id == user.id
                    )
                )
            ).scalars().one()
            sub.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await db.commit()
            fresh = datetime.now(timezone.utc)
            expired_signal = SourceSignal(
                exchange="gate", source_trader_id="32801", symbol="MSTRXUSDT",
                side="short", leverage=1, qty=0, percent=None, action="open",
                source_mode="B", opened_at=fresh, received_at=fresh,
                dedupe_key="e2e-expired", dropped=False,
            )
            db.add(expired_signal)
            await db.commit()
            expired_orders = await copy_engine.handle_signal(expired_signal)
            assert expired_orders[0].status == "failed"
            assert expired_orders[0].failure_category == "risk"
            assert "subscription" in (expired_orders[0].fail_reason or "")
            assert events[-1][1] == "bot.order"
            assert events[-1][2]["status"] == "failed"

        await engine.dispose()

    asyncio.run(scenario())


def test_stopped_strategy_blocks_new_risk_but_emits_failure(monkeypatch):
    """策略关闭后 open/add 必须落失败单并推送；close/reduce 仍由主链保留。"""
    events: list[tuple[int, str, dict]] = []

    async def fake_publish(user_id: int, channel: str, payload: dict) -> None:
        events.append((user_id, channel, payload))

    monkeypatch.setattr("api.ws.broker.publish_user_event", fake_publish)

    class FakeDb:
        def __init__(self, strategy):
            self.strategy = strategy
            self.added = []

        async def get(self, model, key):
            if model is Strategy:
                return self.strategy
            return None

        async def scalar(self, statement):
            return None

        def add(self, value):
            self.added.append(value)

        async def commit(self):
            for i, value in enumerate(self.added, start=1):
                if getattr(value, "id", None) is None:
                    value.id = i

    async def scenario() -> None:
        strategy = type("S", (), {
            "id": 1, "status": "paused", "follow_enabled": False, "gray_pct": 100,
        })()
        db = FakeDb(strategy)
        engine = object.__new__(CopyEngine)
        engine.db = db
        bot = type("B", (), {
            "id": 2, "user_id": 3, "strategy_id": 1, "leverage": 10,
            "exchange": "gate", "api_key_id": 4, "virtual_locked_usdt": 0,
        })()
        sig = type("G", (), {
            "id": 5, "exchange": "gate", "source_trader_id": "32801",
            "symbol": "MSTRXUSDT", "side": "short", "action": "open",
            "percent": None, "source_mode": "B",
        })()
        async def fake_match(self, exchange, trader_id):
            return [bot]

        engine.match_bots = MethodType(fake_match, engine)
        orders = await engine.handle_signal(sig)
        order = orders[0]
        assert order.status == "failed"
        assert order.failure_category == "risk"
        assert [channel for _, channel, _ in events] == ["signal.new", "bot.order"]
        assert events[-1][2]["status"] == "failed"

    asyncio.run(scenario())
