"""为 alice(10000) 补充 12 条奖励记录，触发奖励页分页(每页10)。"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///c:/Users/w6485/Desktop/AI 量化/信号聚合AI/dev.db"

from api.models import User, PaymentOrder, Invite, Reward
from api.core.security import hash_password


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    statuses = ["available", "verifying", "paid", "frozen", "available", "withdrawing",
                "available", "paid", "verifying", "available", "paid", "available"]
    async with Session() as db:
        for i, st in enumerate(statuses):
            suid = 20000 + i
            db.add(User(id=suid, email=f"invitee{i}@test.com", password_hash="x",
                        role="user", is_active=True))
            await db.flush()
            po = PaymentOrder(user_id=suid, plan_id="monthly_19_9u", amount_usdt=19.9,
                              network="trc20", status="confirmed")
            db.add(po)
            await db.flush()
            db.add(Invite(inviter_id=10000, invitee_id=suid, code=f"ALICE-{i}",
                          bound_at=now - timedelta(days=i), locked=False))
            db.add(Reward(
                owner_id=10000, source_user_id=suid, source_payment_order_id=po.id,
                amount_usdt=1.99, status=st,
                verifying_started_at=now - timedelta(days=i),
                verifying_ends_at=(now + timedelta(hours=24)) if st in ("verifying", "withdrawing") else None,
            ))
        await db.commit()
    async with engine.connect() as conn:
        from sqlalchemy import text
        n = (await conn.execute(text("select count(*) from rewards where owner_id=10000"))).scalar()
        print(f"rewards(owner=10000): {n}")
    await engine.dispose()
    print("SEED REWARDS OK")


asyncio.run(main())