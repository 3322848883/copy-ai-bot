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
_EMAIL_CODE_MAX_ATTEMPTS = 5  # ★ H8：错误尝试 ≥5 次即作废
# 开发环境内存验证码存储兜底（Redis 不可用时；生产用 Redis，多实例一致）
_email_codes: dict[str, dict] = {}

_VERIFY_CODE_KEY = "verify_code:{email}"


def _store_email_code(email: str, code: str) -> None:
    """验证码存储：优先 Redis（生产多实例一致），异常降级内存（单实例 dev）。"""
    import json

    from redis import Redis

    record = {
        "code": code,
        "attempts": 0,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=_EMAIL_CODE_TTL_MIN)).isoformat(),
    }
    try:
        r = Redis.from_url(get_settings().redis_url, decode_responses=True)
        r.set(_VERIFY_CODE_KEY.format(email=email), json.dumps(record), ex=_EMAIL_CODE_TTL_MIN * 60)
        return
    except Exception:  # noqa: BLE001
        _email_codes[email] = record


def _get_email_code(email: str) -> dict | None:
    """读取验证码记录：Redis 优先，内存兜底。"""
    import json

    from redis import Redis

    try:
        r = Redis.from_url(get_settings().redis_url, decode_responses=True)
        raw = r.get(_VERIFY_CODE_KEY.format(email=email))
        if raw:
            return json.loads(raw)
        return _email_codes.get(email) or None
    except Exception:  # noqa: BLE001
        return _email_codes.get(email) or None


def _delete_email_code(email: str) -> None:
    from redis import Redis

    try:
        r = Redis.from_url(get_settings().redis_url, decode_responses=True)
        r.delete(_VERIFY_CODE_KEY.format(email=email))
    except Exception:  # noqa: BLE001
        pass
    _email_codes.pop(email, None)


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
        _store_email_code(email, code)

        user = User(email=email, password_hash=hash_password(password), is_active=False)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        # 发送验证码邮件（dev 控制台输出；生产 SMTP）
        await self.mailer.send_verify_code(email, code, ttl_min=_EMAIL_CODE_TTL_MIN)
        return user

    # ── 邮箱验证激活 ──
    async def verify_email(self, email: str, code: str) -> User:
        """验证码激活：校验 6 位码 + 5min TTL + ★ H8 尝试次数限制 → is_active=True。"""
        email = email.strip().lower()
        record = _get_email_code(email)
        if not record:
            raise AuthError("请先注册获取验证码")
        if datetime.now(timezone.utc) > datetime.fromisoformat(record["expires_at"]):
            _delete_email_code(email)
            raise AuthError("验证码已过期，请重新注册")
        if record["attempts"] >= _EMAIL_CODE_MAX_ATTEMPTS:
            _delete_email_code(email)
            raise AuthError("验证码错误次数过多，请重新注册获取新验证码")
        if record["code"] != code.strip():
            record["attempts"] = record.get("attempts", 0) + 1
            # 回写尝试次数（Redis 或内存）
            import json

            from redis import Redis

            try:
                r = Redis.from_url(get_settings().redis_url, decode_responses=True)
                r.set(_VERIFY_CODE_KEY.format(email=email), json.dumps(record), ex=_EMAIL_CODE_TTL_MIN * 60)
            except Exception:  # noqa: BLE001
                _email_codes[email] = record
            raise AuthError("验证码错误")

        user = await self.db.scalar(select(User).where(User.email == email))
        if not user:
            raise NotFoundError("用户不存在")
        user.is_active = True
        await self.db.commit()
        await self.db.refresh(user)
        _delete_email_code(email)
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

    # ── 登出 / 凭证吊销（M6 上线就绪：Redis 吊销时间戳，旧 refresh 全部失效）──
    @staticmethod
    def _revoke_key(user_id: int) -> str:
        return f"refresh_revoked:{user_id}"

    async def logout(self, user_id: int) -> None:
        """吊销该用户全部 refresh token（写 Redis 吊销时间，ttl 7 天）。"""
        import time

        from redis import Redis

        try:
            r = Redis.from_url(get_settings().redis_url, decode_responses=True)
            r.set(self._revoke_key(user_id), str(int(time.time())), ex=7 * 24 * 3600)
        except Exception:  # noqa: BLE001 Redis 不可用不阻断登出
            pass

    async def is_refresh_revoked(self, user_id: int, iat: float) -> bool:
        """refresh 签发时间早于吊销时间 → 已吊销。"""
        from redis import Redis

        try:
            r = Redis.from_url(get_settings().redis_url, decode_responses=True)
            revoked_at = r.get(self._revoke_key(user_id))
        except Exception:  # noqa: BLE001 Redis 不可用则放行
            return False
        if not revoked_at:
            return False
        return (iat or 0) < float(revoked_at)

    # ── 改密 ──
    async def change_password(self, user_id: int, old: str, new: str) -> None:
        user = await self.db.get(User, user_id)
        if not user or not verify_password(old, user.password_hash):
            raise AuthError("原密码错误")
        if len(new) < get_settings().password_min_length:
            raise ConflictError(f"新密码至少 {get_settings().password_min_length} 位")
        user.password_hash = hash_password(new)
        await self.db.commit()
        # 审计留痕
        try:
            from api.services.audit.service import AuditService

            await AuditService(self.db).log(
                actor_id=user_id, action="auth.change_password",
                target_type="user", target_id=str(user_id),
                before=None, after={"password_changed": True},
            )
        except Exception:  # noqa: BLE001 审计失败不阻断改密
            pass
        # 吊销该用户全部旧 refresh
        await self.logout(user_id)

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
