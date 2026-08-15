# auth 模块（M1 T1.2）
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.errors import AuthError, ConflictError, NotFoundError
from api.core.security import create_token, hash_password, verify_password
from api.models.user import User
from api.services.mailer.service import Mailer

_EMAIL_CODE_TTL_MIN = 5  # 验证码 5 分钟 TTL
# 开发环境内存验证码存储（生产用 Redis；无 Redis 时可用，重启失效）
_email_codes: dict[str, dict] = {}


class AuthService:
    def __init__(self, db: AsyncSession, mailer: Mailer | None = None) -> None:
        self.db = db
        self.mailer = mailer or Mailer()

    # ── 注册 ──
    async def register(self, email: str, password: str) -> User:
        """邮箱注册：生成 6 位验证码（5min TTL），用户 is_active=False。"""
        settings = get_settings()
        email = email.strip().lower()
        if len(password) < settings.password_min_length:
            raise ConflictError("密码至少 8 位")

        existing = await self.db.scalar(select(User).where(User.email == email))
        if existing:
            raise ConflictError("邮箱已注册")

        code = f"{random.randint(0, 999999):06d}"
        # dev 环境固定验证码 123456，便于本地端到端测试
        if settings.app_env == "dev":
            code = "123456"
        _email_codes[email] = {
            "code": code,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=_EMAIL_CODE_TTL_MIN),
        }

        user = User(email=email, password_hash=hash_password(password), is_active=False)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        # 发送验证码邮件（dev 控制台输出；生产 SMTP）
        await self.mailer.send_verify_code(email, code, ttl_min=_EMAIL_CODE_TTL_MIN)
        return user

    # ── 邮箱验证激活 ──
    async def verify_email(self, email: str, code: str) -> User:
        """验证码激活：校验 6 位码 + 5min TTL → is_active=True。"""
        email = email.strip().lower()
        record = _email_codes.get(email)
        if not record:
            raise AuthError("请先注册获取验证码")
        if datetime.now(timezone.utc) > record["expires_at"]:
            _email_codes.pop(email, None)
            raise AuthError("验证码已过期，请重新注册")
        if record["code"] != code.strip():
            raise AuthError("验证码错误")

        user = await self.db.scalar(select(User).where(User.email == email))
        if not user:
            raise NotFoundError("用户不存在")
        user.is_active = True
        await self.db.commit()
        await self.db.refresh(user)
        _email_codes.pop(email, None)
        return user

    # ── 登录 ──
    async def login(self, email: str, password: str) -> dict[str, str]:
        """登录：返回 TokenPair（access + refresh）。"""
        email = email.strip().lower()
        user = await self.db.scalar(select(User).where(User.email == email))
        if not user or not verify_password(password, user.password_hash):
            raise AuthError("邮箱或密码错误")
        if not user.is_active:
            raise AuthError("邮箱未激活，请先完成验证码验证")
        if user.is_frozen:
            raise AuthError("账号已被冻结")

        settings = get_settings()
        access = create_token(str(user.id), audience=settings.jwt_audience, token_type="access")
        refresh = create_token(
            str(user.id),
            audience=settings.jwt_audience,
            expires_minutes=settings.jwt_refresh_expire_days * 24 * 60,
            token_type="refresh",
        )
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "risk_disclosure_accepted": user.risk_disclosure_accepted,  # ★ T1.7 前端据此弹强制风险揭示
        }

    # ── 登出（M1 简化：客户端丢弃 refresh；生产维护 jti 黑名单）──
    async def logout(self, jti: str | None = None) -> None:
        # TODO(M6): refresh token 黑名单 / jti 回收
        return None

    # ── 改密 ──
    async def change_password(self, user_id: int, old: str, new: str) -> None:
        user = await self.db.get(User, user_id)
        if not user or not verify_password(old, user.password_hash):
            raise AuthError("原密码错误")
        user.password_hash = hash_password(new)
        await self.db.commit()

    # ── ★ T1.7 强制风险揭示 ──
    async def accept_risk_disclosure(self, user_id: int) -> User:
        """首次登录/首次开启跟单前必须勾选风险揭示（不勾选不可继续）。"""
        user = await self.db.get(User, user_id)
        if not user:
            raise NotFoundError("用户不存在")
        user.risk_disclosure_accepted = True
        await self.db.commit()
        await self.db.refresh(user)
        return user
