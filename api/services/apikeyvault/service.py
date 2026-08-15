# apikeyvault 模块（M1 T1.5/T1.6：绑定实时校验 + AES-256-GCM 加密落库）
from __future__ import annotations

import base64

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.errors import ApiKeyError
from api.core.security import ApiKeyVault
from api.exchange_clients.base import ExchangeAdapter
from api.exchange_clients.registry import get_adapter
from api.models.user import ApiKey
from api.services.audit.service import AuditService

# 失败原因细分（验收门）
FAIL_REASONS = {
    "connect": "网络连接失败，请检查网络或交易所状态",
    "auth": "API Key/Secret 无效（鉴权失败）",
    "withdraw": "检测到提现权限，禁止绑定（合规红线）",
    "missing": "缺少交易权限",
}


class ApiKeyVaultService:
    """API Key 保险库：AES-256-GCM，AAD 绑 user_id|exchange；解密后即用即丢。"""

    def __init__(self, key_hex: str | None = None) -> None:
        self._vault = ApiKeyVault(key_hex)

    def encrypt(self, plaintext: str, aad: str) -> tuple[str, str, str, str]:
        return self._vault.encrypt(plaintext, aad)

    def decrypt(self, ciphertext: str, nonce: str, tag: str, aad_b64: str) -> str:
        return self._vault.decrypt(ciphertext, nonce, tag, aad_b64)


class ApiKeyService:
    """API Key 绑定/解绑（T1.5：ExchangeAdapter 实时校验；拒提现）。"""

    def __init__(self, db: AsyncSession, vault: ApiKeyVaultService, audit: AuditService) -> None:
        self.db = db
        self.vault = vault
        self.audit = audit

    async def bind(
        self,
        *,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        adapter: ExchangeAdapter | None = None,
        ip: str | None = None,
    ) -> ApiKey:
        """实时校验（test_connect → permissions → withdraw 拒绝）→ AES-256-GCM 入库。"""
        adapter = adapter or get_adapter(exchange)

        # 1. 连通性
        try:
            connected = await adapter.test_connect(api_key, api_secret)
        except Exception:
            raise ApiKeyError(FAIL_REASONS["connect"]) from None
        if not connected:
            raise ApiKeyError(FAIL_REASONS["auth"])

        # 2. 权限校验：read=1 AND trade=1 AND withdraw=0（红线）
        perms = await adapter.check_permissions(api_key, api_secret)
        if perms.get("withdraw"):
            raise ApiKeyError(FAIL_REASONS["withdraw"])
        if not perms.get("trade"):
            raise ApiKeyError(FAIL_REASONS["missing"])

        # 3. 加密落库（AAD 绑 user_id|exchange；api_key 与 secret 一起加密）
        aad = f"{user_id}|{exchange}"
        combined = f"{api_key}\n{api_secret}"
        ciphertext, nonce, tag, aad_b64 = self.vault.encrypt(combined, aad)

        existing = await self.db.scalar(
            select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.exchange == exchange)
        )
        if existing:
            raise ApiKeyError("该交易所已绑定 API，请先解绑")

        record = ApiKey(
            user_id=user_id,
            exchange=exchange,
            ciphertext=ciphertext,
            nonce=nonce,
            tag=tag,
            aad=aad_b64,
            status="active",
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        await self.audit.log(
            actor_id=user_id,
            action="apikey.bind",
            target_type="apikey",
            target_id=record.id,
            after={"exchange": exchange, "permissions": perms},
            ip=ip,
        )
        return record

    async def unbind(self, user_id: int, exchange: str, ip: str | None = None) -> None:
        record = await self.db.scalar(
            select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.exchange == exchange)
        )
        if record is None:
            raise ApiKeyError("未找到该交易所的 API 绑定")
        await self.db.delete(record)
        await self.db.commit()
        await self.audit.log(
            actor_id=user_id,
            action="apikey.unbind",
            target_type="apikey",
            target_id=record.id,
            after={"exchange": exchange},
            ip=ip,
        )
