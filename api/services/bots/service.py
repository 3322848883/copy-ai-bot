# bots 模块（M3 T3.2：CopyBot CRUD + 跨所错配拦截）
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.errors import ConflictError, NotFoundError, PermissionDenied, ValidationError
from api.models.bot import CopyBot, CopyOrder, PositionSnapshot
from api.models.signal import Strategy
from api.models.user import ApiKey, Identity
from api.services.tradetracker.service import TradeTracker

logger = logging.getLogger("signal-saas.bots")

BOT_STATUSES = ("active", "paused", "stopped")


class BotService:
    """跟单机器人 CRUD：create / update / pause / resume / delete。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        strategy_id: int,
        exchange: str,
        api_key_id: int,
        amount_mode: str = "percent",
        fixed_amount_usdt: float | None = None,
        percent: float | None = 20.0,
        leverage: int = 10,
        margin_mode: str = "isolated",  # ★ G07
        max_total_position_usdt: float = 10_000.0,
        paper: bool = False,  # ★ M6 T6.2 沙箱模拟盘
    ) -> CopyBot:
        # ★ M5 T5.10：订阅拦截（未订阅/已过期禁止建跟单）
        #   豁免：平台池主号下级（sub_account）或交易所邀请码复核通过（合作归属免订阅）
        from api.services.billing.service import BillingService

        sub = await BillingService(self.db).get_active_subscription(user_id)
        if sub is None:
            _ident = await self.db.get(Identity, user_id)
            _exempt = bool(
                _ident
                and (
                    (_ident.exchange_invite_code and _ident.exchange_invite_status == "approved")
                    or _ident.identity_type == "sub_account"
                )
            )
            if not _exempt:
                if _ident and _ident.exchange_invite_code and _ident.exchange_invite_status == "pending":
                    raise PermissionDenied("交易所邀请码已提交，请等待管理员复核通过后即可跟单")
                raise PermissionDenied("无有效订阅，请先开通套餐，或绑定交易所邀请码并通过管理员复核")

        # ★ M4 修复（合规）：未确认风险揭示禁止建跟单（前端首次跟单弹窗 + 后端强制）
        from sqlalchemy import select as _select

        from api.models.user import User

        user = await self.db.scalar(_select(User).where(User.id == user_id))
        if user is None or not user.risk_disclosure_accepted:
            raise ValidationError("请先阅读并确认风险揭示后再开启跟单")

        # 校验策略存在且上架
        strategy = await self.db.get(Strategy, strategy_id)
        if strategy is None or strategy.status != "listed":
            raise NotFoundError("策略不存在或未上架")
        # ★ 跟单阀门上移后台管理员：管理员关闭跟单则该策略不可创建跟单机器人
        if not strategy.follow_enabled:
            raise ValidationError("该策略当前未开放跟单，敬请期待")
        # ★ 跨所错配拦截：策略所属交易所 vs 机器人交易所
        if strategy.source_exchange != exchange:
            raise ValidationError(
                f"跨所错配：策略来自 {strategy.source_exchange}，不能绑定到 {exchange} 交易所"
            )
        # ★ 模式A只做公开仓位（2026-08-23）：隐藏仓位的带单员公开渠道无方向
        #   （占比接口无 side、实时持仓接口对 is_hide 返回空），模式A open 信号
        #   回退 long 会反向开仓——技术保护（安全拦截，消息友好化）。
        #   模式B（跟单镜像）方向真实，隐藏带单员不受限。
        if strategy.source == "A":
            from api.models.signal import Trader

            trader = await self.db.get(Trader, strategy.trader_id)
            if trader is not None and trader.hide_position:
                raise ValidationError(
                    "该信号源当前为展示型（可查看历史业绩与画像），实时跟单能力接入后即可开启，敬请期待"
                )
        # API Key 归属校验
        api_row = await self.db.get(ApiKey, api_key_id)
        if api_row is None or api_row.user_id != user_id:
            raise ValidationError("API Key 不存在或不属于当前用户")
        if api_row.exchange != exchange:
            raise ValidationError(f"API Key 属于 {api_row.exchange}，与所选交易所不符")

        # 同一策略不重复建 bot
        existing = await self.db.scalar(
            select(CopyBot).where(CopyBot.user_id == user_id, CopyBot.strategy_id == strategy_id)
        )
        if existing:
            raise ConflictError("该策略已创建跟单机器人")

        if amount_mode == "fixed" and (not fixed_amount_usdt or fixed_amount_usdt <= 0):
            raise ValidationError("fixed 模式必须提供正数的 fixed_amount_usdt")
        if amount_mode == "percent" and (not percent or not 0 < percent <= 100):
            raise ValidationError("percent 模式必须在 1-100 之间")
        if margin_mode not in ("isolated", "cross"):
            raise ValidationError("margin_mode 必须为 isolated / cross")

        bot = CopyBot(
            user_id=user_id,
            strategy_id=strategy_id,
            exchange=exchange,
            api_key_id=api_key_id,
            amount_mode=amount_mode,
            fixed_amount_usdt=fixed_amount_usdt if amount_mode == "fixed" else None,
            percent=percent if amount_mode == "percent" else None,
            leverage=leverage,
            margin_mode=margin_mode,
            max_total_position_usdt=max_total_position_usdt,
            virtual_locked_usdt=0.0,
            status="active",
            paper=paper,
        )
        self.db.add(bot)
        await self.db.commit()
        await self.db.refresh(bot)
        return bot

    async def list(self, user_id: int) -> list[dict]:
        bots = (
            await self.db.execute(select(CopyBot).where(CopyBot.user_id == user_id).order_by(CopyBot.id.desc()))
        ).scalars().all()
        out = []
        for bot in bots:
            strategy = await self.db.get(Strategy, bot.strategy_id)
            tracker = TradeTracker(self.db)
            pnl = await tracker.snapshot_pnl(bot)
            out.append(
                {
                    "id": bot.id,
                    "strategy_id": bot.strategy_id,
                    "strategy_name": strategy.display_name if strategy else "未知策略",
                    "exchange": bot.exchange,
                    "amount_mode": bot.amount_mode,
                    "fixed_amount_usdt": bot.fixed_amount_usdt,
                    "percent": bot.percent,
                    "leverage": bot.leverage,
                    "margin_mode": bot.margin_mode,
                    "max_total_position_usdt": bot.max_total_position_usdt,
                    "virtual_locked_usdt": bot.virtual_locked_usdt,
                    "status": bot.status,
                    "paper": bot.paper,  # ★ M6 T6.2 沙箱模拟盘（list 序列化补漏）
                    "pnl": pnl,
                }
            )
        return out

    async def update_status(self, user_id: int, bot_id: int, status: str) -> CopyBot:
        if status not in BOT_STATUSES:
            raise ValidationError("status 非法")
        bot = await self.db.get(CopyBot, bot_id)
        if bot is None or bot.user_id != user_id:
            raise NotFoundError("机器人不存在")
        bot.status = status
        await self.db.commit()
        await self.db.refresh(bot)
        return bot

    async def update(
        self,
        user_id: int,
        bot_id: int,
        *,
        percent: float | None = None,
        leverage: int | None = None,
        margin_mode: str | None = None,
        max_total_position_usdt: float | None = None,
        amount_mode: str | None = None,
        fixed_amount_usdt: float | None = None,
    ) -> CopyBot:
        """修改机器人配置（M6 前端补全）：仅允许 active/paused 状态，参数校验与 create 一致。"""
        bot = await self.db.get(CopyBot, bot_id)
        if bot is None or bot.user_id != user_id:
            raise NotFoundError("机器人不存在")

        if amount_mode == "fixed" and (fixed_amount_usdt is None or fixed_amount_usdt <= 0):
            raise ValidationError("fixed 模式必须提供正数的 fixed_amount_usdt")
        if amount_mode == "percent" and (percent is None or not 0 < percent <= 100):
            raise ValidationError("percent 模式必须在 1-100 之间")
        if margin_mode is not None and margin_mode not in ("isolated", "cross"):
            raise ValidationError("margin_mode 必须为 isolated / cross")
        if leverage is not None and not 1 <= leverage <= 125:
            raise ValidationError("杠杆必须在 1-125 之间")
        if max_total_position_usdt is not None and max_total_position_usdt <= 0:
            raise ValidationError("单笔最大名义价值必须为正数")

        if percent is not None:
            bot.percent = percent
        if leverage is not None:
            bot.leverage = leverage
        if margin_mode is not None:
            bot.margin_mode = margin_mode
        if max_total_position_usdt is not None:
            bot.max_total_position_usdt = max_total_position_usdt
        if amount_mode is not None:
            bot.amount_mode = amount_mode
        if fixed_amount_usdt is not None:
            bot.fixed_amount_usdt = fixed_amount_usdt

        await self.db.commit()
        await self.db.refresh(bot)
        return bot

    async def delete(self, user_id: int, bot_id: int) -> None:
        bot = await self.db.get(CopyBot, bot_id)
        if bot is None or bot.user_id != user_id:
            raise NotFoundError("机器人不存在")
        await self.db.delete(bot)
        await self.db.commit()

    async def get_orders(self, user_id: int, bot_id: int, limit: int = 20) -> list[dict]:
        bot = await self.db.get(CopyBot, bot_id)
        if bot is None or bot.user_id != user_id:
            raise NotFoundError("机器人不存在")
        orders = (
            await self.db.execute(
                select(CopyOrder).where(CopyOrder.bot_id == bot_id).order_by(CopyOrder.id.desc()).limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": o.id,
                "action": o.action,
                "qty": o.qty,
                "filled_qty": o.filled_qty,
                "avg_price": o.avg_price,
                "exchange_order_id": o.exchange_order_id,
                "client_order_id": o.client_order_id,
                "leverage": o.leverage,
                "required_margin_usdt": o.required_margin_usdt,
                "status": o.status,
                "failure_category": o.failure_category,
                "fail_reason": o.fail_reason,
                "latency_ms": o.latency_ms,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "executed_at": o.executed_at.isoformat() if o.executed_at else None,
            }
            for o in orders
        ]

    async def get_positions(self, user_id: int, bot_id: int) -> list[dict]:
        bot = await self.db.get(CopyBot, bot_id)
        if bot is None or bot.user_id != user_id:
            raise NotFoundError("机器人不存在")
        rows = (
            await self.db.execute(
                select(PositionSnapshot)
                .where(PositionSnapshot.bot_id == bot_id, PositionSnapshot.is_open == True)  # noqa: E712
            )
        ).scalars().all()
        return [
            {
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "entry_price": r.entry_price,
                "mark_price": r.mark_price,
                "unrealized_pnl": r.unrealized_pnl,
                "notional_usdt": r.notional_usdt,
            }
            for r in rows
        ]
