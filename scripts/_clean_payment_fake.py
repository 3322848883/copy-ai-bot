"""临时：清理两库假数据 + 生产库补 APTOS 地址。

用户已确认"连演示账号一起清"：删除所有用户及其关联表（支付/订阅/提现/跟单/通知/身份等），
保留平台核心数据（strategies/traders/source_signals/trader_profiles/exchanges 等）与 4 条真实收款地址。
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DSNS = {
    "dev": "postgresql+asyncpg://signal:signal@localhost:5432/signal_saas",
    "prod": "postgresql+asyncpg://signal:paytest-prod-pg-2026@localhost:5433/signal_saas",
}

REAL_ADDR = {
    "trc20": "TPmb4qXKc9deoRuUYPyr19stavDmmnV4pD",
    "bep20": "0x975f3040AecF2d9e93449648D4f8886765843280",
    "erc20": "0x975f3040AecF2d9e93449648D4f8886765843280",
    "aptos": "0x417ec5499355c8bb34870a850de2fd13f9056fa2a336a72c00a8cca1dacd872b",
}

# 用户相关表（子表在前，避免外键冲突）
USER_TABLES = [
    "copy_orders", "position_snapshots", "copy_bots", "rewards", "withdrawals",
    "invites", "notifications", "identity_exchanges", "identities", "api_keys",
    "subscriptions", "payment_orders", "audit_events", "users",
]


async def cleanup(name: str, dsn: str) -> None:
    engine = create_async_engine(dsn)
    async with engine.begin() as conn:
        # 先解除平台收款地址对 users 的引用（updated_by 可空），保证 users 可被删除
        await conn.execute(text("UPDATE platform_addresses SET updated_by = NULL"))

        for t in USER_TABLES:
            try:
                await conn.execute(text(f'DELETE FROM "{t}"'))
                print(f"[{name}] cleared {t}")
            except Exception as ex:  # noqa: BLE001
                print(f"[{name}] (skip) {t}: {ex}")

        # 收款地址：只保留真实 active，删 mock，补齐缺失（prod 补 aptos）
        rows = (await conn.execute(text("SELECT id, network, address FROM platform_addresses"))).all()
        for row in rows:
            _id, n, addr = row[0], row[1], row[2]
            real = REAL_ADDR.get(n)
            keep = real is not None and str(addr).lower() == real.lower()
            if not keep:
                await conn.execute(text("DELETE FROM platform_addresses WHERE id=:id"), {"id": _id})
                print(f"[{name}] removed mock addr id={_id} {n} {addr}")
        have = {(r[1], str(r[2]).lower()) for r in rows}
        for n, addr in REAL_ADDR.items():
            if not any(nn == n and aa == addr.lower() for nn, aa in have):
                await conn.execute(
                    text("INSERT INTO platform_addresses (network, address, status, remark) "
                         "VALUES (:n, :a, 'active', '真实生产收款地址')"),
                    {"n": n, "a": addr},
                )
                print(f"[{name}] inserted real addr {n} = {addr}")
    await engine.dispose()
    print(f"[{name}] DONE")


if __name__ == "__main__":
    for nm, dsn in DSNS.items():
        asyncio.run(cleanup(nm, dsn))