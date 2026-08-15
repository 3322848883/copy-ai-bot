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


def get_current_user(authorization: str = Depends(get_bearer)):
    """JWT 校验（aud=web，前台用户身份）。"""
    from api.core.config import get_settings
    from api.core.errors import AuthError
    from api.core.security import decode_token

    try:
        payload = decode_token(authorization, get_settings().jwt_audience)
    except ValueError as exc:
        raise AuthError("登录已失效，请重新登录") from exc
    if payload.get("type") != "access":
        raise AuthError("无效的令牌类型")
    return int(payload["sub"])


# ── M5 T5.1：后台认证（aud=admin 独立 JWT + RBAC 角色）──
def get_current_admin(authorization: str = Depends(get_bearer)):
    """后台 JWT 校验（aud=admin）+ 管理员身份（admin/reviewer/support）。"""
    from api.core.config import get_settings
    from api.core.errors import AuthError, PermissionDenied
    from api.core.security import decode_token

    try:
        payload = decode_token(authorization, get_settings().jwt_admin_audience)
    except ValueError as exc:
        raise AuthError("后台登录已失效，请重新登录") from exc
    if payload.get("type") != "access":
        raise AuthError("无效的令牌类型")
    role = payload.get("role", "user")
    if role not in ("admin", "reviewer", "support"):
        raise PermissionDenied("无后台访问权限")
    return {"id": int(payload["sub"]), "role": role}


def require_admin(admin: dict = Depends(get_current_admin)):
    """仅 admin 角色。"""
    from api.core.errors import PermissionDenied

    if admin["role"] != "admin":
        raise PermissionDenied("仅管理员可执行此操作")
    return admin
