# admin/auth 路由（M5 T5.1：后台登录，aud=admin 独立 JWT + RBAC + ★ TOTP 双因素 + 失败锁定）
from __future__ import annotations

from time import time

import pyotp
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel
from redis import Redis

from api.core.config import get_settings
from api.core.errors import AuthError
from api.core.security import create_token, decode_token, verify_password
from api.deps import DbDep, get_current_admin
from api.models.user import User

router = APIRouter(prefix="/auth", tags=["admin-auth"])

# ── Redis 键 ──
TOTP_ACTIVE_KEY = "admin:totp:{uid}"            # 已启用 TOTP 密钥（base32）
TOTP_PENDING_KEY = "admin:totp:pending:{uid}"   # 待确认密钥
TOTP_CHALLENGE_KEY = "admin:totp_challenge:{cid}"  # 登录挑战 → user_id
LOGIN_FAIL_KEY = "admin:login_fail:{email}"     # 连续失败计数
LOGIN_LOCK_KEY = "admin:login_lock:{email}"     # 锁定标记（15 分钟）
MAX_FAILS = 5
LOCK_MINUTES = 15
CHALLENGE_TTL = 300  # 5 分钟


class AdminLoginIn(BaseModel):
    email: str
    password: str


class AdminRefreshIn(BaseModel):
    refresh_token: str | None = None  # 缺省时从 httpOnly cookie 读取


class TotpVerifyIn(BaseModel):
    challenge_id: str
    code: str


class TotpSetupIn(BaseModel):
    code: str  # 用当前验证码确认新密钥


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _issue_tokens(db, user: User) -> tuple[str, str]:
    """签发 admin 令牌对（aud=admin + RBAC role）。"""
    settings = get_settings()
    access = create_token(
        subject=str(user.id),
        audience=settings.jwt_admin_audience,
        token_type="access",
        extra={"role": user.role},
    )
    refresh = create_token(
        subject=str(user.id),
        audience=settings.jwt_admin_audience,
        expires_minutes=settings.jwt_refresh_expire_days * 24 * 60,
        token_type="refresh",
        extra={"role": user.role},
    )
    return access, refresh


def _set_admin_cookies(response, access: str, refresh: str) -> None:
    """后台令牌下发：生产经 httpOnly cookie（同域），dev 同时返回 body 兼容。"""
    settings = get_settings()
    secure = settings.app_env != "dev"
    response.set_cookie("ss_admin_access", access, httponly=True, secure=secure,
                        samesite="lax", path="/", max_age=86400)
    response.set_cookie("ss_admin_refresh", refresh, httponly=True, secure=secure,
                        samesite="lax", path="/", max_age=7 * 86400)


def _check_lock(r: Redis, email: str) -> None:
    if r.exists(LOGIN_LOCK_KEY.format(email=email)):
        raise AuthError("连续 5 次密码错误，账号已锁定 15 分钟，请稍后再试")


def _record_fail(r: Redis, email: str) -> None:
    key = LOGIN_FAIL_KEY.format(email=email)
    count = r.incr(key)
    if count == 1:
        r.expire(key, LOCK_MINUTES * 60)
    if count >= MAX_FAILS:
        r.set(LOGIN_LOCK_KEY.format(email=email), "1", ex=LOCK_MINUTES * 60)
        r.delete(key)
        raise AuthError("连续 5 次密码错误，账号已锁定 15 分钟，请稍后再试")
    raise AuthError(f"密码错误，剩余 {MAX_FAILS - count} 次尝试 · 连续 {MAX_FAILS} 次错误将锁定 {LOCK_MINUTES} 分钟")


def _clear_fail(r: Redis, email: str) -> None:
    r.delete(LOGIN_FAIL_KEY.format(email=email))


def _totp_enabled(r: Redis, user_id: int) -> bool:
    secret = r.get(TOTP_ACTIVE_KEY.format(uid=user_id))
    return bool(secret)


@router.post("/login")
async def admin_login(body: AdminLoginIn, db: DbDep = None, response: Response = None) -> dict:
    from sqlalchemy import select

    r = _redis()
    email = body.email.strip().lower()
    _check_lock(r, email)

    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        _record_fail(r, email)
    if not verify_password(body.password, user.password_hash):
        _record_fail(r, email)
    if user.role not in ("admin", "reviewer", "support"):
        raise AuthError("无后台访问权限")
    if user.is_frozen:
        raise AuthError("账号已冻结")
    _clear_fail(r, email)

    # ★ TOTP：已启用则进入双因素挑战（V1.1 后置启用，V1 管理员默认未启用则直登）
    if _totp_enabled(r, user.id):
        challenge_id = f"{int(time() * 1000)}-{user.id}"
        r.set(TOTP_CHALLENGE_KEY.format(cid=challenge_id), str(user.id), ex=CHALLENGE_TTL)
        return {"totp_required": True, "challenge_id": challenge_id, "role": user.role, "email": email}

    access, refresh = _issue_tokens(db, user)
    _set_admin_cookies(response, access, refresh)
    return {"totp_required": False, "access_token": access, "refresh_token": refresh, "role": user.role}


@router.post("/totp-verify")
async def admin_totp_verify(body: TotpVerifyIn, db: DbDep = None, response: Response = None) -> dict:
    """双因素验证：校验 TOTP 动态码 → 签发 admin 令牌对（挑战一次性使用）。"""
    from sqlalchemy import select

    r = _redis()
    uid_raw = r.get(TOTP_CHALLENGE_KEY.format(cid=body.challenge_id.strip()))
    if not uid_raw:
        raise AuthError("验证会话已过期，请重新登录")
    r.delete(TOTP_CHALLENGE_KEY.format(cid=body.challenge_id.strip()))  # 一次性

    secret = r.get(TOTP_ACTIVE_KEY.format(uid=int(uid_raw)))
    if not secret:
        raise AuthError("TOTP 未启用或已失效")
    totp = pyotp.TOTP(secret)
    if not totp.verify(body.code.strip(), valid_window=1):
        raise AuthError("验证码错误或已过期，请重试")

    user = await db.scalar(select(User).where(User.id == int(uid_raw)))
    if user is None or not user.is_active:
        raise AuthError("管理员不存在或已停用")
    if user.is_frozen:
        raise AuthError("账号已被冻结")

    access, refresh = _issue_tokens(db, user)
    _set_admin_cookies(response, access, refresh)
    return {"totp_required": True, "access_token": access, "refresh_token": refresh, "role": user.role}


# ── TOTP 管理（运维启用/停用双因素）──

@router.get("/totp/status")
async def admin_totp_status(admin: dict = Depends(get_current_admin)) -> dict:
    r = _redis()
    return {"enabled": _totp_enabled(r, admin["id"])}


@router.post("/totp/setup")
async def admin_totp_setup(admin: dict = Depends(get_current_admin)) -> dict:
    """生成新密钥与 otpauth URI（存 pending，确认后才生效）。"""
    r = _redis()
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(name=str(admin["id"]), issuer_name="signal-admin")
    r.set(TOTP_PENDING_KEY.format(uid=admin["id"]), secret, ex=600)
    return {"secret": secret, "otpauth_uri": uri}


@router.post("/totp/confirm")
async def admin_totp_confirm(body: TotpSetupIn, admin: dict = Depends(get_current_admin)) -> dict:
    """用当前动态码确认 pending 密钥 → 正式启用。"""
    r = _redis()
    secret = r.get(TOTP_PENDING_KEY.format(uid=admin["id"]))
    if not secret:
        raise AuthError("请先获取 TOTP 密钥")
    if not pyotp.TOTP(secret).verify(body.code.strip(), valid_window=1):
        raise AuthError("验证码错误，请重试")
    r.set(TOTP_ACTIVE_KEY.format(uid=admin["id"]), secret)
    r.delete(TOTP_PENDING_KEY.format(uid=admin["id"]))
    return {"enabled": True}


@router.post("/totp/disable")
async def admin_totp_disable(body: TotpSetupIn, admin: dict = Depends(get_current_admin)) -> dict:
    """输入当前动态码后停用双因素（防误操作）。"""
    r = _redis()
    secret = r.get(TOTP_ACTIVE_KEY.format(uid=admin["id"]))
    if not secret:
        return {"enabled": False}
    if not pyotp.TOTP(secret).verify(body.code.strip(), valid_window=1):
        raise AuthError("验证码错误，请重试")
    r.delete(TOTP_ACTIVE_KEY.format(uid=admin["id"]))
    return {"enabled": False}


@router.post("/refresh")
async def admin_refresh(body: AdminRefreshIn, request: Request, response: Response, db: DbDep = None) -> dict:
    """★ 生产修复：后台刷新令牌（cookie 优先 / body 兜底）→ 重签 TokenPair + RBAC。"""
    settings = get_settings()
    token = body.refresh_token or request.cookies.get("ss_admin_refresh") or ""
    if not token:
        raise AuthError("刷新令牌缺失")
    try:
        payload = decode_token(token, settings.jwt_admin_audience)
    except ValueError as exc:
        raise AuthError("刷新令牌无效或已过期") from exc
    if payload.get("type") != "refresh":
        raise AuthError("无效的令牌类型")
    role = payload.get("role", "user")
    if role not in ("admin", "reviewer", "support"):
        raise AuthError("无后台访问权限")
    user = await db.scalar(select(User).where(User.id == int(payload["sub"])))
    if user is None or not user.is_active:
        raise AuthError("管理员不存在或已停用")
    if user.is_frozen:
        raise AuthError("账号已被冻结")
    # 吊销检查（logout/改密后旧 refresh 失效）
    from api.services.auth.service import AuthService

    if await AuthService(db).is_refresh_revoked(int(payload["sub"]), float(payload.get("iat") or 0)):
        raise AuthError("刷新令牌已失效，请重新登录")

    access, refresh = _issue_tokens(db, user)
    if response is not None:
        _set_admin_cookies(response, access, refresh)
    return {"access_token": access, "refresh_token": refresh, "role": role}


@router.post("/logout")
async def admin_logout(db: DbDep, response: Response, authorization: str = Header("")) -> dict:
    """后台登出：吊销该管理员全部 refresh + 清 cookie。"""
    user_id: int | None = None
    if authorization.startswith("Bearer "):
        try:
            payload = decode_token(authorization[7:], get_settings().jwt_admin_audience)
            if payload.get("type") == "access":
                user_id = int(payload["sub"])
        except Exception:  # noqa: BLE001 无效 token 忽略
            pass
    if user_id is not None:
        from api.services.auth.service import AuthService

        await AuthService(db).logout(user_id)
    response.delete_cookie("ss_admin_access", path="/")
    response.delete_cookie("ss_admin_refresh", path="/")
    return {"ok": True}
