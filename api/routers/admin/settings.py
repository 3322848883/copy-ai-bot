# admin/settings 路由（后台「系统设置」：验证码/模板/套餐/邀请/链上确认）
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.core.errors import ValidationError
from api.deps import DbDep, get_current_admin, require_admin
from api.services.settings import service as settings_svc
from api.services.audit.service import AuditService

router = APIRouter(prefix="/settings", tags=["admin-settings"])


class RuleIn(BaseModel):
    key: str
    value: bool | float | int | str


class TemplateIn(BaseModel):
    key: str
    subject: str
    html: str


class SnapshotIn(BaseModel):
    data: dict


class PlanIn(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=64)
    price_usdt: float = Field(gt=0)
    duration_days: int = Field(gt=0)
    trial: bool = False
    max_purchase: int | None = None
    enabled: bool = True


@router.get("/rules")
async def get_rules(_admin=Depends(get_current_admin)) -> dict:
    """全部平台参数（含默认值归一化）。"""
    return {"rules": settings_svc.get_all_rules(), "meta": settings_svc.PLATFORM_RULES}


@router.post("/rules")
async def set_rule(body: RuleIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """更新平台参数（audit 留痕）。"""
    meta = settings_svc.PLATFORM_RULES.get(body.key)
    if meta is None:
        raise ValidationError(f"未知设置项: {body.key}")
    settings_svc.set_rule(body.key, body.value)
    await AuditService(db).log(
        actor_id=admin["id"], action="settings.rule_update",
        target_type="setting", target_id=body.key,
        before={"value": settings_svc.get_rule(body.key)}, after={"value": body.value},
    )
    return {"key": body.key, "value": body.value}


@router.post("/rules/batch")
async def set_rules_batch(body: SnapshotIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """批量更新平台参数（一次性保存，全量审计留痕）。"""
    changed = []
    for key, value in body.data.items():
        if key not in settings_svc.PLATFORM_RULES:
            continue
        settings_svc.set_rule(key, value)
        changed.append(key)
    await AuditService(db).log(
        actor_id=admin["id"], action="settings.rules_batch_update",
        target_type="setting", target_id="batch",
        after={"keys": changed},
    )
    return {"updated": changed}


# ── 邮件模板 ──
@router.get("/templates")
async def get_templates(_admin=Depends(get_current_admin)) -> dict:
    out = {}
    for key in settings_svc.TEMPLATE_SUBJECTS:
        subject, html = settings_svc.get_template(key)
        out[key] = {"key": key, "subject": subject, "html": html}
    return {"templates": out}


@router.post("/templates")
async def set_template(body: TemplateIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """保存邮件模板（audit 留痕）。"""
    if body.key not in settings_svc.TEMPLATE_SUBJECTS:
        raise ValidationError(f"未知模板: {body.key}")
    settings_svc.set_template(body.key, body.subject, body.html)
    await AuditService(db).log(
        actor_id=admin["id"], action="settings.template_update",
        target_type="template", target_id=body.key,
        after={"subject": body.subject},
    )
    return {"key": body.key, "subject": body.subject}


# ── 订阅套餐 ──
@router.get("/plans")
async def get_plans(_admin=Depends(get_current_admin)) -> dict:
    return {"plans": settings_svc.get_plans()}


@router.post("/plans")
async def upsert_plan(body: PlanIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """新增/更新套餐（audit 留痕）。"""
    plans = settings_svc.get_plans()
    existing = next((p for p in plans if p.get("plan_id") == body.plan_id), None)
    if existing:
        existing.update(body.model_dump())
    else:
        plans.append(body.model_dump())
    settings_svc.save_plans(plans)
    await AuditService(db).log(
        actor_id=admin["id"], action="settings.plan_upsert",
        target_type="plan", target_id=body.plan_id,
        after={"name": body.name, "price_usdt": body.price_usdt},
    )
    return {"plan_id": body.plan_id}


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """删除套餐（audit 留痕）。"""
    plans = settings_svc.get_plans()
    remaining = [p for p in plans if p.get("plan_id") != plan_id]
    if len(remaining) == len(plans):
        raise ValidationError(f"套餐不存在: {plan_id}")
    settings_svc.save_plans(remaining)
    await AuditService(db).log(
        actor_id=admin["id"], action="settings.plan_delete",
        target_type="plan", target_id=plan_id,
        after={"deleted": True},
    )
    return {"plan_id": plan_id, "deleted": True}