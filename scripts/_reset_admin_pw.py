import asyncio
import sys
sys.path.insert(0, ".")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from api.core.config import get_settings
from api.core.security import hash_password


async def main():
    s = get_settings()
    engine = create_async_engine(s.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        hashed = hash_password("AdminTest123!")
        await db.execute(
            text("UPDATE users SET password_hash = :h, is_active = true WHERE email = 'admin@local.test'"),
            {"h": hashed},
        )
        await db.commit()
    await engine.dispose()
    print("admin password reset OK")


asyncio.run(main())
