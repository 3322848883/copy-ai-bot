"""安全组件：JWT 签发/校验、bcrypt 密码、AES-256-GCM 凭证保险库。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from api.core.config import get_settings

_ALGO = "HS256"


# ── 密码 ──
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


# ── JWT（M1 T1.2 完整实现）──
from jose import JWTError, jwt


def create_token(
    subject: str,
    audience: str | None = None,
    expires_minutes: int | None = None,
    token_type: str = "access",
    extra: dict[str, Any] | None = None,
) -> str:
    """签发 JWT。aud 区分前台(web)/后台(admin)，完全隔离。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "aud": audience or settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes),
        "type": token_type,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def decode_token(token: str, audience: str) -> dict[str, Any]:
    """校验 JWT（校验签名 + 过期 + audience）。"""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO], audience=audience)
    except JWTError as exc:
        raise ValueError(f"invalid token: {exc}") from exc


# ── AES-256-GCM 凭证保险库（M1 T1.6 完善）──
class ApiKeyVault:
    """AES-256-GCM 加密 API Key；AAD 绑定 user_id|exchange|key_id。"""

    def __init__(self, key_hex: str | None = None):
        settings = get_settings()
        key = bytes.fromhex(key_hex or settings.vault_key_hex)
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, aad: str) -> tuple[str, str, str, str]:
        """返回 (ciphertext_b64, nonce_b64, tag_b64, aad_b64)。"""
        nonce = os.urandom(12)
        ct = self._aead.encrypt(nonce, plaintext.encode(), aad.encode())
        # ct 尾部 16 字节为 tag
        tag, body = ct[-16:], ct[:-16]
        return (
            base64.urlsafe_b64encode(body).decode(),
            base64.urlsafe_b64encode(nonce).decode(),
            base64.urlsafe_b64encode(tag).decode(),
            base64.urlsafe_b64encode(aad.encode()).decode(),
        )

    def decrypt(self, ciphertext_b64: str, nonce_b64: str, tag_b64: str, aad_b64: str) -> str:
        body = base64.urlsafe_b64decode(ciphertext_b64)
        nonce = base64.urlsafe_b64decode(nonce_b64)
        tag = base64.urlsafe_b64decode(tag_b64)
        aad = base64.urlsafe_b64decode(aad_b64).decode()
        plain = self._aead.decrypt(nonce, body + tag, aad.encode())
        return plain.decode()


# ── 交易所签名（决策 B，各所实现见 exchange_clients/signing.py）──
def hmac_sha512(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()
