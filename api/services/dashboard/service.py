# dashboard 模块（M6 P0：首页数据看板聚合）
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.billing import Subscription
from api.models.bot import CopyBot, CopyOrder
from api.models.signal import Strategy
from api.models.user import ApiKey
from api.services.billing.service import BillingService
from api.services.bots.service import BotService
from api.services.ledger.service import LedgerService

logger = logging.getLogger("signal-saas.dashboard")

# 首页实时行情（dev mock；生产接交易所公开 ticker）
_TICKERS: list[dict] = [
    {"symbol": "BTC_USDT", "price": 64040.8, "change_pct": 2.34},
    {"symbol": "ETH_USDT", "price": 3287.4, "change_pct": -1.12},
    {"symbol": "SOL_USDT", "price": 148.92, "change_pct": 5.67},
    {"symbol": "DOGE_USDT", "price": 0.1542, "change_pct": -0.84},
]


class DashboardService:
    """首页数据看板：4 指标卡 + 新手引导 + 我的跟单 + 实时行情 + 最近订单。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_dashboard(self, user_id: int) -> dict:
        ledger = LedgerService(self.db)
        balance = await ledger.balance(user_id)

        bots = await BotService(self.db).list(user_id)
        running = [b for b in bots if b["status"] == "active"]
        total_pnl = sum(b["pnl"]["unrealized_pnl_usdt"] for b in bots)

        # 订阅
        sub = await BillingService(self.db).get_active_subscription(user_id)
        sub_info = {"active": False}
        if sub is not None:
            expires = sub.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            days_left = max(0, (expires - datetime.now(timezone.utc)).days)
            sub_info = {
                "active": True,
                "plan_id": sub.plan_id,
                "expires_at": expires.isoformat(),
                "days_left": days_left,
            }

        # 新手引导（G23：has_api + has_bot 时隐藏）
        has_api = await self.db.scalar(
            select(ApiKey.id).where(ApiKey.user_id == user_id).limit(1)
        ) is not None
        has_bot = len(bots) > 0
        onboarding = {
            "has_api": has_api,
            "has_bot": has_bot,
            "step": 3 if has_bot else (2 if has_api else 1),
        }

        recent_orders = await self._recent_orders(user_id)

        return {
            "metrics": {
                "available_usdt": balance["available_usdt"],
                "total_reward_usdt": balance["total_usdt"],
                "running_bots": len(running),
                "total_bots": len(bots),
                "total_pnl_usdt": round(total_pnl, 2),
                "subscription": sub_info,
            },
            "onboarding": onboarding,
            "bots": bots,
            "recent_orders": recent_orders,
            "tickers": _TICKERS,
        }

    async def _recent_orders(self, user_id: int, limit: int = 8) -> list[dict]:
        """最近跟单订单：按用户机器人关联 CopyOrder，倒序取最近 limit 条。"""
        bot_ids = (
            await self.db.execute(select(CopyBot.id).where(CopyBot.user_id == user_id))
        ).scalars().all()
        if not bot_ids:
            return []
        rows = (
            await self.db.execute(
                select(CopyOrder)
                .where(CopyOrder.bot_id.in_(bot_ids))
                .order_by(CopyOrder.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        bots = {
            b.id: b
            for b in (
                await self.db.execute(select(CopyBot).where(CopyBot.id.in_(bot_ids)))
            ).scalars().all()
        }
        strategy_names = {
            s.id: s.display_name
            for s in (
                await self.db.execute(select(Strategy).where(Strategy.id.in_([b.strategy_id for b in bots.values()])))
            ).scalars().all()
        }
        out = []
        for o in rows:
            bot = bots.get(o.bot_id)
            out.append(
                {
                    "id": o.id,
                    "bot_id": o.bot_id,
                    "strategy_name": strategy_names.get(bot.strategy_id) if bot else None,
                    "action": o.action,
                    "qty": o.qty,
                    "status": o.status,
                    "failure_category": o.failure_category,
                    "latency_ms": o.latency_ms,
                    "executed_at": o.executed_at.isoformat() if o.executed_at else None,
                }
            )
        return out
