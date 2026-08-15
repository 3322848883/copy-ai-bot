# -*- coding: utf-8 -*-
"""e2e 数据清理：按 e2e_ 前缀删除测试产生的用户及关联数据（保留 admin）。"""
from __future__ import annotations

import asyncio

import asyncpg

DSN = "postgresql://signal:signal@localhost:5433/signal_saas"

# 删除顺序：先子表后父表（FK 约束）。排除 admin（e2e_docker_admin 保留）
E2E_USERS = "(SELECT id FROM users WHERE email LIKE 'e2e_%' AND email NOT LIKE 'e2e_docker_admin%')"
E2E_EMAILS = "email LIKE 'e2e_%' AND email NOT LIKE 'e2e_docker_admin%'"
STATEMENTS = [
    f"DELETE FROM audit_events WHERE actor_id IN {E2E_USERS}",
    f"DELETE FROM withdrawals WHERE user_id IN {E2E_USERS}",
    f"DELETE FROM rewards WHERE owner_id IN {E2E_USERS} OR source_user_id IN {E2E_USERS}",
    f"DELETE FROM subscriptions WHERE user_id IN {E2E_USERS}",
    f"DELETE FROM payment_orders WHERE user_id IN {E2E_USERS}",
    f"DELETE FROM copy_orders WHERE bot_id IN (SELECT id FROM copy_bots WHERE user_id IN {E2E_USERS})",
    f"DELETE FROM position_snapshots WHERE bot_id IN (SELECT id FROM copy_bots WHERE user_id IN {E2E_USERS})",
    f"DELETE FROM copy_bots WHERE user_id IN {E2E_USERS}",
    "DELETE FROM strategies WHERE trader_id IN (SELECT id FROM traders WHERE trader_id LIKE 'e2e_%')",
    "DELETE FROM trader_profiles WHERE trader_id IN (SELECT id FROM traders WHERE trader_id LIKE 'e2e_%')",
    "DELETE FROM traders WHERE trader_id LIKE 'e2e_%'",
    f"DELETE FROM api_keys WHERE user_id IN {E2E_USERS}",
    f"DELETE FROM identities WHERE user_id IN {E2E_USERS}",
    f"DELETE FROM identity_exchanges WHERE identity_user_id IN {E2E_USERS}",
    f"DELETE FROM invites WHERE inviter_id IN {E2E_USERS} OR invitee_id IN {E2E_USERS}",
    "DELETE FROM exchange_invite_codes WHERE code LIKE 'E2E%'",
    f"DELETE FROM users WHERE {E2E_EMAILS}",
]


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        for sql in STATEMENTS:
            try:
                res = await conn.execute(sql)
                print(f"{res}: {sql.split(' FROM ')[0].strip()}")
            except Exception as exc:  # noqa: BLE001
                print(f"SKIP {sql[:60]}... → {exc}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
