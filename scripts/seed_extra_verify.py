"""临时补测数据：给 alice 建提现记录；新增策略让广场分页出现。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///c:/Users/w6485/Desktop/AI 量化/信号聚合AI/dev.db"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from api.models import Withdrawal, Strategy


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        db.add_all([
            Withdrawal(user_id=10000, amount_usdt=100, fee_usdt=1.0, network="trc20",
                       address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", status="pending_review"),
            Withdrawal(user_id=10000, amount_usdt=50, fee_usdt=1.0, network="bep20",
                       address="0x742d35Cc6634C0532925a3b844Bc520A0b0F0e5a", status="paid",
                       tx_hash="0xabc123def4567890abc123def4567890abc123def4567890abc123def4567890"),
            Withdrawal(user_id=10000, amount_usdt=20, fee_usdt=1.0, network="trc20",
                       address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", status="rejected",
                       reject_reason="地址与实名信息不一致"),
        ])
        for i in range(15):
            db.add(Strategy(trader_id=1, source_exchange="gate", display_name=f"灰度策略 {i + 1}",
                            style="momentum", risk_rating="mid", gray_pct=100, status="listed"))
        await db.commit()
    await engine.dispose()
    print("EXTRA VERIFY OK")


asyncio.run(main())