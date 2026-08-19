# admins 管理路由（管理员账户管理：创建/编辑/角色调整/冻结/重置密码，全程审计留痕）
from __future__ import annotations

import re
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy import select

from api.core.config import get_settings
from api.core.errors import AuthError, ConflictError, NotFoundError, PermissionDenied, ValidationError
from api.core.security import hash_password, verify_password
from api.deps import DbDep, require_admin
from api.models.user import User
from api.services.audit.service import AuditService

router = APIRouter(prefix="/admins", tags=["admin-admins"])

# ★ 与 seed_prod_admin.py 口径一致：后台账户密码至少 12 位
STAFF_ROLES = ("admin", "reviewer", "support")
ADMIN_PASSWORD_MIN = 12
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 改密/降权后强制重新登录：iat 早于该时间点的旧令牌（access+refresh）全部失效
REAUTH_KEY = "admin:reauth:{uid}"


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def force_reauth(uid: int) -> None:
    """作废指定管理员全部现存令牌（TTL=refresh 最长有效期，过期后键自动清理）。"""
    settings = get_settings()
    try:
        _redis().set(REAUTH_KEY.format(uid=uid), str(time.time()), ex=settings.jwt_refresh_expire_days * 24 * 3600)
    except Exception:
        # Redis 不可用时降级：令牌自然过期（access ≤24h），不阻塞改密操作
        pass


class CreateIn(BaseModel):
    email: str
    password: str
    role: str = "admin"
    admin_note: str | None = Field(default=None, max_length=2000)


class UpdateIn(BaseModel):
    email: str | None = None
    role: str | None = None
    admin_note: str | None = None


class PasswordIn(BaseModel):
    new_password: str


class SelfPasswordIn(BaseModel):
    old_password: str
    new_password: str


class FreezeIn(BaseModel):
    frozen: bool


def _to_dict(u: User, current_id: int) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "is_frozen": u.is_frozen,
        "admin_note": u.admin_note,
        "is_self": u.id == current_id,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


async def _other_active_admins(db, exclude_id: int) -> int:
    """除指定账户外仍可用的 admin 数量（保证后台永不锁死）。"""
    rows = (
        await db.execute(
            select(User.id).where(
                User.role == "admin",
                User.is_active.is_(True),
                User.is_frozen.is_(False),
                User.id != exclude_id,
            )
        )
    ).scalars().all()
    return len(rows)


async def _get_staff(db, admin_id: int) -> User:
    u = await db.get(User, admin_id)
    if u is None or u.role not in STAFF_ROLES:
        raise NotFoundError("后台账户不存在")
    return u


@router.get("")
async def list_admins(db: DbDep = None, admin=Depends(require_admin)) -> dict:
    rows = (
        await db.execute(select(User).where(User.role.in_(STAFF_ROLES)).order_by(User.id.asc()))
    ).scalars().all()
    return {"items": [_to_dict(u, admin["id"]) for u in rows]}


@router.post("")
async def create_admin(body: CreateIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValidationError("邮箱格式不正确")
    if body.role not in STAFF_ROLES:
        raise ValidationError("角色仅支持 admin / reviewer / support")
    if len(body.password) < ADMIN_PASSWORD_MIN:
        raise ValidationError(f"密码至少 {ADMIN_PASSWORD_MIN} 位")
    if await db.scalar(select(User).where(User.email == email)):
        raise ConflictError("该邮箱已被注册")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        is_active=True,
        role=body.role,
        risk_disclosure_accepted=True,
        admin_note=(body.admin_note or "").strip() or None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await AuditService(db).log(
        actor_id=admin["id"], action="admin.create",
        target_type="user", target_id=str(user.id),
        after={"email": user.email, "role": user.role},
    )
    return _to_dict(user, admin["id"])


@router.patch("/me/password")
async def change_own_password(body: SelfPasswordIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """自助改密：需验证原密码，成功后本人全部令牌立即作废。"""
    user = await db.get(User, admin["id"])
    if user is None or not verify_password(body.old_password, user.password_hash):
        raise AuthError("原密码错误")
    if len(body.new_password) < ADMIN_PASSWORD_MIN:
        raise ValidationError(f"新密码至少 {ADMIN_PASSWORD_MIN} 位")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    force_reauth(user.id)
    await AuditService(db).log(
        actor_id=admin["id"], action="admin.password_change",
        target_type="user", target_id=str(user.id),
        after={"password_changed": True},
    )
    return {"id": user.id, "password_changed": True}


@router.patch("/{admin_id}")
async def update_admin(admin_id: int, body: UpdateIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    user = await _get_staff(db, admin_id)
    before = {"email": user.email, "role": user.role, "admin_note": user.admin_note}
    changed = False
    role_changed = False

    if body.email is not None:
        email = body.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise ValidationError("邮箱格式不正确")
        if email != user.email:
            if await db.scalar(select(User).where(User.email == email, User.id != admin_id)):
                raise ConflictError("该邮箱已被其他账户使用")
            user.email = email
            changed = True

    if body.role is not None:
        if body.role not in STAFF_ROLES:
            raise ValidationError("角色仅支持 admin / reviewer / support")
        if body.role != user.role:
            if user.id == admin["id"]:
                raise PermissionDenied("不能修改自己的角色")
            # 降掉最后一个可用 admin 会导致后台锁死
            if user.role == "admin" and await _other_active_admins(db, admin_id) == 0:
                raise ConflictError("系统至少需保留一个可用的管理员，无法降权")
            user.role = body.role
            changed = True
            role_changed = True

    if body.admin_note is not None:
        note = body.admin_note.strip() or None
        if note != user.admin_note:
            user.admin_note = note
            changed = True

    if not changed:
        return _to_dict(user, admin["id"])
    await db.commit()
    if role_changed:
        force_reauth(user.id)  # 降权即时生效：旧令牌（含旧角色声明）作废
    await AuditService(db).log(
        actor_id=admin["id"], action="admin.update",
        target_type="user", target_id=str(admin_id),
        before=before,
        after={"email": user.email, "role": user.role, "admin_note": user.admin_note},
    )
    return _to_dict(user, admin["id"])


@router.patch("/{admin_id}/password")
async def reset_admin_password(admin_id: int, body: PasswordIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """管理员强制重置他人密码（无需原密码），目标账户全部令牌立即作废。"""
    user = await _get_staff(db, admin_id)
    if len(body.new_password) < ADMIN_PASSWORD_MIN:
        raise ValidationError(f"密码至少 {ADMIN_PASSWORD_MIN} 位")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    force_reauth(user.id)
    await AuditService(db).log(
        actor_id=admin["id"], action="admin.password_reset",
        target_type="user", target_id=str(admin_id),
        after={"password_changed": True},
    )
    return {"id": admin_id, "password_changed": True}


@router.patch("/{admin_id}/freeze")
async def freeze_admin(admin_id: int, body: FreezeIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    user = await _get_staff(db, admin_id)
    if user.id == admin["id"]:
        raise PermissionDenied("不能冻结自己的账户")
    if user.is_frozen == body.frozen:
        return {"id": admin_id, "is_frozen": user.is_frozen}
    if body.frozen and user.role == "admin" and await _other_active_admins(db, admin_id) == 0:
        raise ConflictError("系统至少需保留一个可用的管理员，无法冻结")
    before = user.is_frozen
    user.is_frozen = body.frozen
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="admin.freeze" if body.frozen else "admin.unfreeze",
        target_type="user", target_id=str(admin_id),
        before={"is_frozen": before}, after={"is_frozen": user.is_frozen},
    )
    return {"id": admin_id, "is_frozen": user.is_frozen}
