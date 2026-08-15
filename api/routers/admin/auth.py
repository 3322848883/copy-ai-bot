# admin/auth 路由（M5 T5.1：后台登录，aud=admin 独立 JWT + RBAC）
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.core.config import get_settings
from api.core.errors import AuthError
from api.core.security import create_token, verify_password
from api.deps import DbDep
from api.models.user import User

router = APIRouter(prefix="/auth", tags=["admin-auth"])


class AdminLoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
async def admin_login(body: AdminLoginIn, db: DbDep = None) -> dict:
    """后台登录：校验用户存在 + 角色 ∈ (admin, reviewer, support) + 密码。"""
    from sqlalchemy import select

    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active:
        raise AuthError("账号或密码错误")
    if not verify_password(body.password, user.password_hash):
        raise AuthError("账号或密码错误")
    if user.role not in ("admin", "reviewer", "support"):
        raise AuthError("无后台访问权限")
    if user.is_frozen:
        raise AuthError("账号已冻结")

    settings = get_settings()
    access = create_token(
        subject=str(user.id),
        audience=settings.jwt_admin_audience,
        token_type="access",
        extra={"role": user.role},
    )
    return {"access_token": access, "role": user.role}
