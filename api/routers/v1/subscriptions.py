# subscriptions 路由（M4 T4.2：套餐 + 订阅状态）
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import DbDep, get_current_user
from api.services.billing.service import BillingService, PLANS

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("/plans")
async def list_plans() -> dict:
    return {"plans": [{"plan_id": pid, **p} for pid, p in PLANS.items()]}


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
