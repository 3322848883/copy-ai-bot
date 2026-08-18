"""临时：把 APTOS 收款地址同步到 dev 库（localhost:5432/signal_saas）。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PG_DSN = "postgresql+asyncpg://signal:signal@localhost:5432/signal_saas"

APTOS = "0x417ec5499355c8bb34870a850de2fd13f9056fa2a336a72c00a8cca1dacd872b"


async def main() -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from api.models.billing import PlatformAddress

    engine = create_async_engine(PG_DSN, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        row = (await db.execute(select(PlatformAddress).where(PlatformAddress.network == "aptos"))).scalars().first()
        if row:
            row.address = APTOS
            row.status = "active"
            row.remark = "真实支付测试·APTOS"
            print(f"update address aptos = {APTOS}")
        else:
            db.add(PlatformAddress(network="aptos", address=APTOS, status="active", remark="真实支付测试·APTOS"))
            print(f"insert address aptos = {APTOS}")
        await db.commit()
    await engine.dispose()
    print("done")


asyncio.run(main())