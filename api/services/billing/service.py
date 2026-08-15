# billing 模块（M4 T4.2：套餐定义 + 限购 + 订阅激活）
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.errors import ConflictError, NotFoundError, ValidationError
from api.models.billing import PaymentOrder, Subscription

logger = logging.getLogger("signal-saas.billing")

# 套餐定义（设计蓝本 §5.2）
PLANS: dict[str, dict] = {
    "trial_5u": {"name": "试用套餐", "price_usdt": 5.0, "duration_days": 7, "trial": True, "max_purchase": 1},
    "monthly_19_9u": {"name": "正式套餐", "price_usdt": 19.9, "duration_days": 30, "trial": False, "max_purchase": None},
}


class BillingService:
    """套餐购买 / 订阅激活 / 有效期查询。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def get_plan(self, plan_id: str) -> dict:
        plan = PLANS.get(plan_id)
        if plan is None:
            raise NotFoundError("套餐不存在")
        return {"plan_id": plan_id, **plan}

    def list_plans(self) -> list[dict]:
        return [{"plan_id": pid, **p} for pid, p in PLANS.items()]

    async def can_purchase(self, user_id: int, plan_id: str) -> None:
        """★ 5U 试用限购 1 次（DB 强校验）。"""
        plan = PLANS.get(plan_id)
        if plan is None:
            raise NotFoundError("套餐不存在")
        if plan.get("trial"):
            count = await self.db.scalar(
                select(PaymentOrder).where(
                    PaymentOrder.user_id == user_id,
                    PaymentOrder.plan_id == plan_id,
                )
            )
            if count is not None:
                raise ConflictError("试用套餐限购 1 次")

    async def activate_subscription(self, user_id: int, plan_id: str, payment_order_id: int) -> Subscription:
        """支付确认后激活订阅（先过期旧订阅，再建新订阅）。"""
        plan = PLANS[plan_id]
        # 使旧订阅过期
        old = (
            await self.db.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id, Subscription.status == "active")
            )
        ).scalars().all()
        for s in old:
            s.status = "expired"

        now = datetime.now(timezone.utc)
        sub = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            status="active",
            expires_at=now + timedelta(days=plan["duration_days"]),
            payment_order_id=payment_order_id,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def get_active_subscription(self, user_id: int) -> Subscription | None:
        """★ G10 配合：风控引擎判断订阅是否有效。"""
        sub = (
            await self.db.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id, Subscription.status == "active")
                .order_by(Subscription.expires_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if sub is None:
            return None
        # SQLite 不保留 tzinfo，读回为 naive；统一按 UTC 处理
        expires = sub.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            sub.status = "expired"
            await self.db.commit()
            return None
        return sub
