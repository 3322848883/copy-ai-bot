"""补种 alice 的跟单机器人 + 持仓 + 订单（首页看板演示数据，幂等）。"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./dev.db"

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from api.models import CopyBot, CopyOrder, PositionSnapshot


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        # 幂等：清掉 alice 已有机器人（连带清理其订单/持仓）
        existing = (await db.execute(select(CopyBot).where(CopyBot.user_id == 10000))).scalars().all()
        for b in existing:
            await db.execute(delete(CopyOrder).where(CopyOrder.bot_id == b.id))
            await db.execute(delete(PositionSnapshot).where(PositionSnapshot.bot_id == b.id))
            await db.delete(b)
        await db.flush()

        bot = CopyBot(
            user_id=10000, strategy_id=1, exchange="gate", api_key_id=1,
            amount_mode="percent", percent=20.0, leverage=10, margin_mode="isolated",
            max_total_position_usdt=10000, virtual_locked_usdt=1200, status="active", paper=False,
        )
        db.add(bot)
        await db.flush()

        db.add(PositionSnapshot(
            bot_id=bot.id, symbol="ETHUSDT", side="long", qty=0.5, entry_price=3200,
            mark_price=3350, unrealized_pnl=75.0, notional_usdt=1675, is_open=True,
        ))
        db.add(PositionSnapshot(
            bot_id=bot.id, symbol="BTCUSDT", side="long", qty=0.02, entry_price=63500,
            mark_price=64040, unrealized_pnl=10.8, notional_usdt=1280.8, is_open=True,
        ))
        now = datetime.now(timezone.utc)
        for act, status, cat, latency, qty in [
            ("open", "filled", None, 320, 0.5),
            ("open", "filled", None, 290, 0.02),
            ("add", "filled", None, 305, 0.1),
            ("close", "filled", None, 288, 0.3),
            ("open", "failed", "balance", None, 0.0),
        ]:
            db.add(CopyOrder(
                bot_id=bot.id, signal_id=1, action=act, qty=qty, leverage=10,
                required_margin_usdt=160, status=status, failure_category=cat,
                latency_ms=latency,
                executed_at=now if status == "filled" else None,
            ))

        await db.commit()
        print("SEED BOT OK, bot_id =", bot.id)

    async with engine.connect() as conn:
        from sqlalchemy import text
        for t in ["copy_bots", "copy_orders", "position_snapshots"]:
            n = (await conn.execute(text(f"select count(*) from {t}"))).scalar()
            print(f"{t}: {n}")
    await engine.dispose()


asyncio.run(main())
