# auth 路由（M1 T1.2 / T1.7；M6 上线就绪：httpOnly cookie）
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, Header, Request, Response

from api.core.config import get_settings
from api.deps import DbDep, get_current_user
from api.schemas.auth import ChangePasswordIn
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


class RefreshIn(BaseModel):
    refresh_token: str | None = None  # 缺省时从 httpOnly cookie 读取


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    """生产（同域 nginx 反代）经 httpOnly cookie 下发令牌；dev 同时返回 body 兼容。"""
    settings = get_settings()
    secure = settings.app_env != "dev"
    response.set_cookie("ss_access", access, httponly=True, secure=secure,
                        samesite="lax", path="/", max_age=86400)
    response.set_cookie("ss_refresh", refresh, httponly=True, secure=secure,
                        samesite="lax", path="/v1/auth", max_age=7 * 86400)


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
async def login(body: LoginIn, db: DbDep, response: Response) -> dict:
    svc = AuthService(db)
    tokens = await svc.login(body.email, body.password)
    _set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    return tokens


@router.post("/refresh")
async def refresh_token(body: RefreshIn, request: Request, response: Response, db: DbDep) -> dict:
    """★ M1 T1.3 刷新令牌：cookie 优先（同域），body 兜底（dev 跨域）→ 签发新 TokenPair。"""
    from api.core.errors import AuthError
    from api.core.security import create_token, decode_token
    from sqlalchemy import select

    from api.models.user import User

    token = body.refresh_token or request.cookies.get("ss_refresh") or ""
    if not token:
        raise AuthError("刷新令牌缺失")
    try:
        payload = decode_token(token, get_settings().jwt_audience)
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
    # M6：登出/改密后旧 refresh 吊销检查（iat < 吊销时间 → 拒绝）
    if await AuthService(db).is_refresh_revoked(int(payload["sub"]), float(payload.get("iat") or 0)):
        raise AuthError("刷新令牌已失效，请重新登录")

    access = create_token(str(user.id), audience=settings.jwt_audience, token_type="access")
    refresh = create_token(
        str(user.id),
        audience=settings.jwt_audience,
        expires_minutes=settings.jwt_refresh_expire_days * 24 * 60,
        token_type="refresh",
    )
    _set_auth_cookies(response, access, refresh)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@router.post("/logout")
async def logout(db: DbDep, response: Response, authorization: str = Header("")) -> dict:
    """登出：清 httpOnly cookie；若带 access token 则吊销该用户全部 refresh。"""
    user_id: int | None = None
    if authorization.startswith("Bearer "):
        try:
            from api.core.security import decode_token

            payload = decode_token(authorization[7:], get_settings().jwt_audience)
            if payload.get("type") == "access":
                user_id = int(payload["sub"])
        except Exception:  # noqa: BLE001 无效 token 忽略
            pass
    if user_id is not None:
        await AuthService(db).logout(user_id)
    response.delete_cookie("ss_access", path="/")
    response.delete_cookie("ss_refresh", path="/v1/auth")
    return {"ok": True}


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, db: DbDep, user_id: int = Depends(get_current_user)) -> dict:
    """改密：校验原密码 → 更新 + 审计 + 吊销旧 refresh。"""
    await AuthService(db).change_password(user_id, body.old_password, body.new_password)
    return {"ok": True, "message": "密码已修改，请重新登录"}


@router.post("/accept-risk-disclosure")
async def accept_risk_disclosure(db: DbDep, user_id: int = Depends(get_current_user)) -> dict:
    svc = AuthService(db)
    user = await svc.accept_risk_disclosure(user_id)
    return {"message": "风险揭示已确认", "risk_disclosure_accepted": user.risk_disclosure_accepted}
