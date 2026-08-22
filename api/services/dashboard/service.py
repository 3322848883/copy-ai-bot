# dashboard 模块（M6 P0：首页数据看板聚合）
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.bot import CopyBot, CopyOrder
from api.models.signal import Strategy
from api.models.user import ApiKey
from api.services.billing.service import BillingService
from api.services.bots.service import BotService
from api.services.ledger.service import LedgerService

logger = logging.getLogger("signal-saas.dashboard")

# 首页实时行情：Gate 公开 ticker（免鉴权）。进程内缓存 10s；任何异常返回空列表（前端隐藏区块，绝不造假数据）
_TICKER_PAIRS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT"]
_TICKER_TTL = 10.0
_ticker_cache: list[dict] = []
_ticker_fetched_at: float = 0.0
_ticker_lock = asyncio.Lock()


async def _fetch_tickers() -> list[dict]:
    """并发拉取 Gate 现货公开行情，失败/超时返回 []。"""
    global _ticker_cache, _ticker_fetched_at

    async def _get_pair(client: httpx.AsyncClient, pair: str) -> dict | None:
        r = await client.get("/spot/tickers", params={"currency_pair": pair})
        r.raise_for_status()
        items = r.json()
        if not isinstance(items, list) or not items:
            return None
        t = items[0]
        return {
            "symbol": pair,
            "price": float(t["last"]),
            "change_pct": round(float(t.get("change_percentage") or 0), 2),
        }

    now = time.monotonic()
    if _ticker_cache and now - _ticker_fetched_at < _TICKER_TTL:
        return _ticker_cache
    async with _ticker_lock:
        if _ticker_cache and time.monotonic() - _ticker_fetched_at < _TICKER_TTL:
            return _ticker_cache
        try:
            async with httpx.AsyncClient(base_url="https://api.gateio.ws/api/v4", timeout=8.0) as client:
                rows = await asyncio.gather(*(_get_pair(client, p) for p in _TICKER_PAIRS), return_exceptions=True)
            out = [r for r in rows if isinstance(r, dict)]
            if out:
                _ticker_cache = out
                _ticker_fetched_at = time.monotonic()
            return out
        except Exception:  # noqa: BLE001 行情失败不影响看板其余数据
            return []


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
            "tickers": await _fetch_tickers(),
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
                    "fail_reason": o.fail_reason,
                    "latency_ms": o.latency_ms,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                    "executed_at": o.executed_at.isoformat() if o.executed_at else None,
                }
            )
        return out
