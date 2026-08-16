"""VAULT_KEY_HEX 轮换演练（M6 T6.7 清单 §4）。

流程：先解密存量全部 API Key（旧密钥）→ 再用新密钥重加密落库 → 留审计记录。
安全约束：
  - 必须显式提供 OLD_VAULT_KEY_HEX 与 NEW_VAULT_KEY_HEX（均 64 位 hex，非全 0）
  - 任一记录解密失败即整体回滚（不允许半途而废导致密钥不一致）
  - 演练后建议挑选一个用户做连通性验证

用法：
  OLD_VAULT_KEY_HEX=<old> NEW_VAULT_KEY_HEX=<new> DATABASE_URL=<url> python scripts/rotate_vault_key.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.core.security import ApiKeyVault
from api.models.user import ApiKey


def _load_hex(name: str) -> str:
    value = os.environ.get(name, "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise SystemExit(f"{name} 必须是 64 位 hex 非空密钥")
    if value == "0" * 64:
        raise SystemExit(f"{name} 不能为全 0")
    return value.lower()


async def main() -> None:
    old_key = _load_hex("OLD_VAULT_KEY_HEX")
    new_key = _load_hex("NEW_VAULT_KEY_HEX")
    db_url = os.environ["DATABASE_URL"] or "sqlite+aiosqlite:///./dev.db"
    if old_key == new_key:
        raise SystemExit("新旧密钥相同，无需轮换")

    engine = create_async_engine(db_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    old_vault = ApiKeyVault(old_key)
    new_vault = ApiKeyVault(new_key)

    async with Session() as db:
        rows = (await db.execute(ApiKey.__table__.select())).all()
        if not rows:
            print("[rotate] 无 API Key 记录，跳过")
            return
        print(f"[rotate] 共 {len(rows)} 条 API Key 待轮换")

        updates = []
        try:
            for row in rows:
                aad = f"{row.user_id}|{row.exchange}"
                plain = old_vault.decrypt(row.ciphertext, row.nonce, row.tag, row.aad)
                ct, nonce, tag, aad_b64 = new_vault.encrypt(plain, aad)
                updates.append((row.id, ct, nonce, tag, aad_b64))
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            raise SystemExit(f"[rotate] 解密失败，已回滚，未写入任何变更：{exc}") from exc

        for rid, ct, nonce, tag, aad_b64 in updates:
            await db.execute(
                ApiKey.__table__.update()
                .where(ApiKey.__table__.c.id == rid)
                .values(ciphertext=ct, nonce=nonce, tag=tag, aad=aad_b64)
            )
        await db.commit()
        print(f"[rotate] 完成：{len(updates)} 条记录已用新密钥重加密")
        print("[rotate] 建议：轮换后挑 1 个用户做一次绑定连通性验证，确认可正常解密")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())