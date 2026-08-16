# subscriptions 路由（M4 T4.2：套餐 + 订阅状态）
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import DbDep, get_current_user
from api.services.settings import service as settings_svc

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("/plans")
async def list_plans(db: DbDep = None) -> dict:
    from api.services.billing.service import BillingService

    return {"plans": BillingService(db).list_plans()}


@router.get("/me")
async def my_subscription(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = BillingService(db)
    sub = await svc.get_active_subscription(user_id)
    if sub is None:
        return {"active": False}
    return {
        "active": True,
        "plan_id": sub.plan_id,
        "expires_at": sub.expires_at.isoformat(),
    }
