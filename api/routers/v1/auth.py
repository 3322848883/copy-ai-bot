# auth 路由（M1 T1.2 / T1.7）
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends

from api.deps import DbDep, get_current_user
from api.services.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class VerifyEmailIn(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
async def register(body: RegisterIn, db: DbDep) -> dict:
    svc = AuthService(db)
    user = await svc.register(body.email, body.password)
    return {"message": "验证码已发送（5 分钟内有效）", "user_id": user.id}


@router.post("/verify-email")
async def verify_email(body: VerifyEmailIn, db: DbDep) -> dict:
    svc = AuthService(db)
    await svc.verify_email(body.email, body.code)
    return {"message": "邮箱验证成功，请登录"}


@router.post("/login")
async def login(body: LoginIn, db: DbDep) -> dict:
    svc = AuthService(db)
    tokens = await svc.login(body.email, body.password)
    return tokens


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh_token(body: RefreshIn, db: DbDep) -> dict:
    """★ M1 T1.3 刷新令牌：校验 refresh（type=refresh + aud=web）→ 签发新 TokenPair。"""
    from api.core.config import get_settings
    from api.core.errors import AuthError
    from api.core.security import create_token, decode_token
    from sqlalchemy import select

    from api.models.user import User

    try:
        payload = decode_token(body.refresh_token, get_settings().jwt_audience)
    except ValueError as exc:
        raise AuthError("刷新令牌无效或已过期") from exc
    if payload.get("type") != "refresh":
        raise AuthError("无效的令牌类型")

    settings = get_settings()
    user = await db.scalar(select(User).where(User.id == int(payload["sub"])))
    if user is None or not user.is_active:
        raise AuthError("用户不存在或未激活")
    if user.is_frozen:
        raise AuthError("账号已被冻结")

    access = create_token(str(user.id), audience=settings.jwt_audience, token_type="access")
    refresh = create_token(
        str(user.id),
        audience=settings.jwt_audience,
        expires_minutes=settings.jwt_refresh_expire_days * 24 * 60,
        token_type="refresh",
    )
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@router.post("/accept-risk-disclosure")
async def accept_risk_disclosure(db: DbDep, user_id: int = Depends(get_current_user)) -> dict:
    svc = AuthService(db)
    user = await svc.accept_risk_disclosure(user_id)
    return {"message": "风险揭示已确认", "risk_disclosure_accepted": user.risk_disclosure_accepted}
