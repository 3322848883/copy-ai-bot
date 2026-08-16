# billing 模块（M4 T4.2：套餐定义 + 限购 + 订阅激活）
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.errors import ConflictError, NotFoundError
from api.models.billing import PaymentOrder, Subscription
from api.services.settings import service as settings_svc

logger = logging.getLogger("signal-saas.billing")


class BillingService:
    """套餐购买 / 订阅激活 / 有效期查询。套餐后台可增删改。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _plan(self, plan_id: str) -> dict:
        plan = settings_svc.get_plan(plan_id)
        if plan is None or not plan.get("enabled", True):
            raise NotFoundError("套餐不存在")
        return plan

    def get_plan(self, plan_id: str) -> dict:
        plan = self._plan(plan_id)
        return {"plan_id": plan_id, "name": plan["name"], "price_usdt": plan["price_usdt"],
                "duration_days": plan["duration_days"], "trial": plan.get("trial", False),
                "max_purchase": plan.get("max_purchase")}

    def list_plans(self) -> list[dict]:
        return [{"plan_id": p["plan_id"], "name": p["name"], "price_usdt": p["price_usdt"],
                 "duration_days": p["duration_days"], "trial": p.get("trial", False),
                 "max_purchase": p.get("max_purchase")}
                for p in settings_svc.get_plans() if p.get("enabled", True)]

    async def can_purchase(self, user_id: int, plan_id: str) -> None:
        """★ 5U 试用限购 1 次（DB 强校验）。"""
        plan = self._plan(plan_id)
        if plan.get("trial"):
            # ★ 生产修复：仅统计已确认订单，失败/作废/超时不占用试用限购名额
            count = await self.db.scalar(
                select(func.count()).select_from(PaymentOrder).where(
                    PaymentOrder.user_id == user_id,
                    PaymentOrder.plan_id == plan_id,
                    PaymentOrder.status == "confirmed",
                )
            )
            if count:
                raise ConflictError("试用套餐限购 1 次")

    async def activate_subscription(self, user_id: int, plan_id: str, payment_order_id: int) -> Subscription:
        """支付确认后激活订阅（先过期旧订阅，再建新订阅）。"""
        plan = self._plan(plan_id)
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
