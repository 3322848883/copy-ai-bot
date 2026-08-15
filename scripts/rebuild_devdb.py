"""重建 dev.db：用当前代码模型 create_all + seed 测试数据（含管理员）。"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ★ 修复：相对路径（跨平台）；须在项目根目录运行
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./dev.db"

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from api.db.base import Base
from api.models import (
    User, Identity, ExchangeInviteCode, PlatformPool, AuditEvent,
)
from api.core.security import hash_password

DB = "c:/Users/w6485/Desktop/AI 量化/信号聚合AI/dev.db"


async def main():
    if os.path.exists(DB):
        os.remove(DB)

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        # 用户
        users = [
            User(id=9999, email="inviter_a@test.com", password_hash="x", role="user", is_active=True),
            User(id=10000, email="alice@test.com", password_hash=hash_password("test123456"), role="user", is_active=True),
            User(id=10001, email="carol@test.com", password_hash=hash_password("test123456"), role="user", is_active=True),
            User(id=10002, email="bob@test.com", password_hash=hash_password("test123456"), role="user", is_active=True),
            User(id=10003, email="dave@test.com", password_hash=hash_password("test123456"), role="user", is_active=True),
            User(id=10004, email="admin@test.com", password_hash=hash_password("admin123456"), role="admin", is_active=True, risk_disclosure_accepted=True),
        ]
        db.add_all(users)
        await db.flush()

        # 身份
        db.add_all([
            Identity(user_id=9999, exchange="gate", invite_code="FRIEND-A", identity_type="normal", locked=True),
            Identity(user_id=10000, exchange="gate", invite_code="FRIEND-A", exchange_invite_code="BNB001", inviter_id=9999, identity_type="normal"),
            Identity(user_id=10001, exchange="binance", identity_type="normal"),
            Identity(user_id=10002, exchange="gate", invite_code="SIGNAL-8F3K2A", identity_type="sub_account"),
            Identity(user_id=10003, exchange="gate", invite_code="FRIEND-A", inviter_id=9999, identity_type="normal"),
        ])

        # 交易所邀请码
        db.add_all([
            ExchangeInviteCode(exchange="gate", code="8F3K2A", status="active", remark="官网A", bind_count=1),
            ExchangeInviteCode(exchange="gate", code="X9B2C7", status="inactive", remark="旧渠道", bind_count=0, max_binds=500),
            ExchangeInviteCode(exchange="binance", code="BNB001", status="active", remark="BNB渠道", bind_count=1, max_binds=1),
        ])

        # 平台池
        db.add(PlatformPool(invite_code="SIGNAL-8F3K2A", exchange="gate", label="官方A", is_active=True))

        # 审计事件（review.done 需要）
        now = datetime.now(timezone.utc)
        db.add_all([
            AuditEvent(actor_id=10004, action="review.approve", target_type="identity", target_id="10002", reason="人工复核通过", after='{"identity_type":"sub_account"}', created_at=now),
            AuditEvent(actor_id=10004, action="review.reject", target_type="identity", target_id="10001", reason="所选所与池码所不匹配", after='{"identity_type":"normal"}', created_at=now),
        ])

        await db.commit()

    async with engine.connect() as conn:
        for t in ["users", "identities", "exchange_invite_codes", "platform_pool", "audit_events"]:
            n = (await conn.execute(text(f"select count(*) from {t}"))).scalar()
            print(f"{t}: {n}")
    await engine.dispose()
    print("REBUILD OK")


asyncio.run(main())
