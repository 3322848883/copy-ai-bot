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
    from sqlalchemy import select

    from api.models.user import Identity
    from api.services.billing.service import BillingService

    svc = BillingService(db)
    sub = await svc.get_active_subscription(user_id)

    # ★ 合作归属免订阅：平台池主号下级（sub_account）或交易所邀请码复核通过（approved）
    identity = await db.scalar(select(Identity).where(Identity.user_id == user_id))
    exchange_invite_bound = bool(
        identity and identity.exchange_invite_code and identity.exchange_invite_status == "approved"
    )
    sub_account = bool(identity and identity.identity_type == "sub_account")
    exempt = exchange_invite_bound or sub_account
    # 复核状态透出给前端展示（待复核/驳回提示）
    exchange_invite_status = (
        identity.exchange_invite_status if identity and identity.exchange_invite_code else None
    )

    if sub is None:
        return {
            "active": exempt,  # 免订阅用户视为有使用权限
            "exempt": exempt,
            "exempt_reason": (
                "exchange_invite" if exchange_invite_bound
                else "sub_account" if sub_account else None
            ),
            "exchange_invite_status": exchange_invite_status,
        }
    return {
        "active": True,
        "plan_id": sub.plan_id,
        "expires_at": sub.expires_at.isoformat(),
        "exempt": exempt,
        "exempt_reason": (
            "exchange_invite" if exchange_invite_bound
            else "sub_account" if sub_account else None
        ),
        "exchange_invite_status": exchange_invite_status,
    }
