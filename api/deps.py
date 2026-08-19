"""全局依赖：db session、auth、audit、services 容器。"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db

DbDep = Annotated[AsyncSession, Depends(get_db)]


class ServiceContainer:
    """app startup 创建一次，持有全部服务实例与共享依赖（M1 T0.3 完善）。"""

    def __init__(self) -> None:
        self._services: dict[str, object] = {}

    def register(self, name: str, service: object) -> None:
        self._services[name] = service

    def get(self, name: str) -> object:
        return self._services[name]


_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def get_bearer(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Bearer Token")
    return authorization.removeprefix("Bearer ")


async def get_current_user(db: DbDep, authorization: str = Depends(get_bearer)):
    """JWT 校验（aud=web，前台用户身份）+ ★ M4 修复：DB 实时状态校验（冻结/停用即拒）。"""
    from api.core.config import get_settings
    from api.core.errors import AuthError
    from api.core.security import decode_token
    from sqlalchemy import select

    from api.models.user import User

    try:
        payload = decode_token(authorization, get_settings().jwt_audience)
    except ValueError as exc:
        raise AuthError("登录已失效，请重新登录") from exc
    if payload.get("type") != "access":
        raise AuthError("无效的令牌类型")
    user_id = int(payload["sub"])
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise AuthError("用户不存在或未激活")
    if user.is_frozen:
        raise AuthError("账号已被冻结")
    return user_id


# ── M5 T5.1：后台认证（aud=admin 独立 JWT + RBAC 角色）──
async def get_current_admin(db: DbDep, authorization: str = Depends(get_bearer)):
    """后台 JWT 校验（aud=admin）+ 管理员身份（admin/reviewer/support）+ ★ M4 DB 状态校验。"""
    from api.core.config import get_settings
    from api.core.errors import AuthError, PermissionDenied
    from api.core.security import decode_token
    from sqlalchemy import select

    from api.models.user import User

    try:
        payload = decode_token(authorization, get_settings().jwt_admin_audience)
    except ValueError as exc:
        raise AuthError("后台登录已失效，请重新登录") from exc
    if payload.get("type") != "access":
        raise AuthError("无效的令牌类型")
    role = payload.get("role", "user")
    if role not in ("admin", "reviewer", "support"):
        raise PermissionDenied("无后台访问权限")
    admin_id = int(payload["sub"])
    user = await db.scalar(select(User).where(User.id == admin_id))
    if user is None or not user.is_active:
        raise AuthError("管理员不存在或已停用")
    if user.is_frozen:
        raise AuthError("账号已被冻结")
    # ★ 改密/降权后旧令牌即刻作废（iat 早于 reauth 时间点即拒绝；Redis 不可用时降级放行）
    from api.core.errors import AuthError as _AuthError

    try:
        from redis import Redis

        changed = Redis.from_url(get_settings().redis_url, decode_responses=True).get(
            f"admin:reauth:{admin_id}"
        )
        if changed and float(payload.get("iat") or 0) < float(changed):
            raise _AuthError("凭证已变更，请重新登录")
    except _AuthError:
        raise
    except Exception:
        pass
    return {"id": admin_id, "role": role}


def require_admin(admin: dict = Depends(get_current_admin)):
    """仅 admin 角色。"""
    from api.core.errors import PermissionDenied

    if admin["role"] != "admin":
        raise PermissionDenied("仅管理员可执行此操作")
    return admin
