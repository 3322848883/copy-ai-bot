# CopyEngine（M3 T3.2/T3.3：机器人匹配 + G03 action 路由 + 执行链）
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.errors import ValidationError
from api.exchange_clients.registry import get_adapter
from api.models.bot import CopyBot, CopyOrder, PositionSnapshot
from api.models.exchange import ContractSpec
from api.models.signal import SourceSignal, Strategy, Trader
from api.models.user import ApiKey
from api.services.copyengine.sizer import Contract, InsufficientBalance, PositionSizer
from api.services.executor.service import ExecResult, OrderRouter
from api.services.riskengine.service import OrderIntent, RiskEngine

logger = logging.getLogger("signal-saas.copyengine")


class CopyEngine:
    """信号 → 活跃机器人 → 换算 → 风控 → 下单 → CopyOrder 落库。

    ★ G03：按 action 路由（OPEN/ADD/REDUCE/CLOSE）
    ★ G10：订阅过期拦截（risk-engine 前置）
    ★ G07：set_margin_mode + set_leverage（OrderRouter 内部）
    """

    def __init__(self, db: AsyncSession, risk: RiskEngine | None = None, router: OrderRouter | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.risk = risk or RiskEngine()
        self.router = router or OrderRouter()
        # ★ M5 T5.8：紧急制动/每日亏损限额从 Redis 读取（后台风控面板可配置）
        self.risk.register_hook(self._load_global_risk)

    def _load_global_risk(self, intent: OrderIntent) -> None:
        """运行时从 Redis 注入紧急制动与每日亏损限额。"""
        try:
            from redis import Redis

            r = Redis.from_url(get_settings().redis_url, decode_responses=True)
            intent.emergency_stop = r.get("risk:emergency_stop") == "1"
            limit = r.get("risk:daily_loss_limit")
            if limit:
                intent.daily_loss_limit = -abs(float(limit))
        except Exception:  # noqa: BLE001 Redis 不可用时保持默认
            pass

    # ── T3.3 信号 → 机器人匹配 ──
    async def match_bots(self, exchange: str, trader_id: str) -> list[CopyBot]:
        """按策略（trader）拉取 active 机器人（★ G10：跳过订阅已过期用户）。"""
        stmt = (
            select(CopyBot)
            .join(Strategy, Strategy.id == CopyBot.strategy_id)
            .where(
                CopyBot.status == "active",
                Strategy.source_exchange == exchange,
                Strategy.trader_id.in_(
                    select(Trader.id).where(Trader.trader_id == trader_id)
                ),
            )
        )
        bots = (await self.db.execute(stmt)).scalars().all()
        return list(bots)

    # ── 处理单条信号（完整执行链）──
    async def handle_signal(self, sig: SourceSignal) -> list[CopyOrder]:
        """处理一条新信号：匹配 → 每 bot 换算 → 风控 → 执行 → 落库。"""
        bots = await self.match_bots(sig.exchange, sig.source_trader_id)
        orders: list[CopyOrder] = []
        for bot in bots:
            # ★ M6 T5.19：signal.new 实时推送（通知匹配该策略的机器人主人）
            try:
                from api.ws.hub import hub

                await hub.push(
                    bot.user_id,
                    "signal.new",
                    {
                        "signal_id": sig.id,
                        "strategy_id": bot.strategy_id,
                        "symbol": sig.symbol,
                        "side": sig.side,
                        "action": sig.action,
                        "percent": sig.percent,
                        "source_mode": sig.source_mode,
                    },
                )
            except Exception:  # noqa: BLE001
                pass
            order = await self._process_bot(bot, sig)
            if order is not None:
                orders.append(order)
        return orders

    @staticmethod
    def _gray_allowed(strategy_id: int, user_id: int, gray_pct: int) -> bool:
        """★ M6 T6.1：稳定哈希放量，同一用户对同一策略结果恒定。"""
        if gray_pct >= 100:
            return True
        if gray_pct <= 0:
            return False
        bucket = hash(f"{strategy_id}:{user_id}") % 100
        return bucket < gray_pct

    async def _process_bot(self, bot: CopyBot, sig: SourceSignal) -> CopyOrder | None:
        """单个机器人的处理链。"""
        # ★ M6 T6.1 灰度发布：strategy.gray_pct < 100 时按 user 哈希放量
        from api.models.signal import Strategy

        strategy = await self.db.get(Strategy, bot.strategy_id)
        if strategy is None:
            return None
        if not self._gray_allowed(strategy.id, bot.user_id, strategy.gray_pct):
            logger.info("bot %s gray-skipped: strategy %s pct=%s", bot.id, strategy.id, strategy.gray_pct)
            return None

        # 跨所错配拦截（T3.2 前置）
        if bot.exchange != sig.exchange:
            order = self._fail_order(bot, sig, "symbol", "跨所错配: 机器人交易所与信号不一致")
            self.db.add(order)
            await self.db.commit()
            return order

        # 拉取 API 凭据
        api_key_row = await self.db.get(ApiKey, bot.api_key_id)
        if api_key_row is None:
            order = self._fail_order(bot, sig, "permission", "API 凭据不存在")
            self.db.add(order)
            await self.db.commit()
            return order
        from api.services.apikeyvault.service import ApiKeyVaultService

        plain = ApiKeyVaultService(get_settings().vault_key_hex).decrypt(
            api_key_row.ciphertext, api_key_row.nonce, api_key_row.tag, api_key_row.aad
        )
        parts = plain.split("\n", 1)
        api_key_plain = parts[0]
        api_secret = parts[1] if len(parts) > 1 else ""
        api_key_row.api_key = api_key_plain  # 供执行使用

        # ★ G03 action 路由
        if sig.action == "close":
            return await self._exec_close(bot, sig, api_key_row, api_secret)
        if sig.action == "reduce":
            return await self._exec_reduce(bot, sig, api_key_row, api_secret)
        return await self._exec_open_add(bot, sig, api_key_row, api_secret)

    # ── OPEN/ADD ──
    async def _exec_open_add(self, bot: CopyBot, sig: SourceSignal, api_row, api_secret: str) -> CopyOrder:
        contract = await self._get_contract(sig.exchange, sig.symbol)
        if contract is None:
            return self._fail_order(bot, sig, "symbol", f"合约规格缺失: {sig.symbol}")

        balance = await self._get_free_balance(bot, api_row, api_secret)
        sizer = PositionSizer(contract)
        try:
            intent = sizer.compute(
                amount_mode=bot.amount_mode,
                fixed_amount_usdt=bot.fixed_amount_usdt,
                percent=self._effective_percent(bot, sig),
                account_free_usdt=balance,
                leverage=bot.leverage,
            )
        except InsufficientBalance as exc:
            return self._fail_order(bot, sig, "balance", exc.message)
        except ValidationError as exc:
            return self._fail_order(bot, sig, "min_size" if "名义" in exc.message else "other", exc.message)

        # 风控
        risk_res = await self.risk.evaluate(
            OrderIntent(
                user_id=bot.user_id,
                bot_id=bot.id,
                strategy_id=bot.strategy_id,
                exchange=bot.exchange,
                symbol=sig.symbol,
                action=sig.action,
                margin_usdt=intent.margin_usdt,
                signal_received_at=sig.received_at,
                source_mode=sig.source_mode,
                subscription_active=await self._subscription_active(bot.user_id),
                identity_type="normal",
                bot_virtual_locked=bot.virtual_locked_usdt,
                bot_max_total_position=bot.max_total_position_usdt,
            )
        )
        # ★ M6 T6.2 指标：风控决策
        try:
            from api.core import metrics as M

            M.risk_decisions_total.labels(decision="approved" if not risk_res.rejected else "rejected").inc()
            M.signal_received_total.labels(exchange=bot.exchange, source=sig.source_mode or "A").inc()
        except Exception:  # noqa: BLE001
            pass
        if risk_res.rejected:
            return self._fail_order(bot, sig, "risk", f"{risk_res.rule}: {risk_res.reason}", latency=risk_res.latency_ms)

        side = "buy" if sig.side == "long" else "sell"
        exec_res = await self._execute_order(
            bot=bot, sig=sig, side=side, qty=intent.qty,
            leverage=bot.leverage, margin_mode=bot.margin_mode, reduce_only=False,
            api_key=api_row.api_key, api_secret=api_secret,
        )
        return await self._finalize(bot, sig, intent.qty, intent.margin_usdt, exec_res, api_row)

    # ── REDUCE：按比例减仓 ──
    async def _exec_reduce(self, bot: CopyBot, sig: SourceSignal, api_row, api_secret: str) -> CopyOrder:
        pos = await self._current_position(bot, api_row, api_secret, sig.symbol)
        if pos is None or pos["qty"] <= 0:
            return self._fail_order(bot, sig, "other", "无持仓可减")
        reduce_qty = pos["qty"] * min(getattr(sig, "reduce_ratio", 0.5) or 0.5, 1.0)
        side = "sell" if sig.side == "long" else "buy"
        exec_res = await self._execute_order(
            bot=bot, sig=sig, side=side, qty=reduce_qty,
            leverage=bot.leverage, margin_mode=bot.margin_mode, reduce_only=True,
            api_key=api_row.api_key, api_secret=api_secret,
        )
        return await self._finalize(bot, sig, reduce_qty, 0.0, exec_res, api_row)

    # ── CLOSE：全部平仓 ──
    async def _exec_close(self, bot: CopyBot, sig: SourceSignal, api_row, api_secret: str) -> CopyOrder:
        pos = await self._current_position(bot, api_row, api_secret, sig.symbol)
        if pos is None or pos["qty"] <= 0:
            return self._fail_order(bot, sig, "other", "无持仓可平")
        side = "sell" if sig.side == "long" else "buy"
        exec_res = await self._execute_order(
            bot=bot, sig=sig, side=side, qty=pos["qty"],
            leverage=bot.leverage, margin_mode=bot.margin_mode, reduce_only=True,
            api_key=api_row.api_key, api_secret=api_secret,
        )
        return await self._finalize(bot, sig, pos["qty"], 0.0, exec_res, api_row)

    # ── helpers ──
    @staticmethod
    def _effective_percent(bot, sig) -> float:
        """★ qty 换算：按带单员持仓占比缩放下单比例（percent × 保证金）。

        - 真实 feed 信号带 leader 占比 percent∈[0,1]（如 0.20=20%），
          下单比例 = bot.percent × leader_percent，镜像带单员组合分配；
        - 批量/WS 信号无占比（None）→ 用 bot.percent（保持原行为）。
        仅对 open 生效；add/reduce/close 走既有持仓路径，不缩放。
        """
        percent = float(bot.percent or 0)
        if sig.action != "open":
            return percent
        leader = getattr(sig, "percent", None)
        if leader is None:
            return percent
        try:
            leader = max(0.0, min(1.0, float(leader)))  # 截断到 [0,1]
        except (TypeError, ValueError):
            return percent
        return round(percent * leader, 6)

    def _fail_order(self, bot, sig, category: str, reason: str, latency: int = 0) -> CopyOrder:
        logger.warning("bot %s fail(%s): %s", bot.id, category, reason)
        return CopyOrder(
            bot_id=bot.id, signal_id=sig.id, action=sig.action, qty=0,
            leverage=bot.leverage, required_margin_usdt=0, status="failed",
            failure_category=category, latency_ms=latency,
        )

    async def _finalize(self, bot, sig, qty: float, margin: float, exec_res: ExecResult, api_row) -> CopyOrder:
        status = "filled" if exec_res.success else "failed"
        order = CopyOrder(
            bot_id=bot.id, signal_id=sig.id, action=sig.action, qty=qty,
            leverage=bot.leverage, required_margin_usdt=margin, status=status,
            failure_category=None if exec_res.success else (exec_res.failure_category or "other"),
            latency_ms=exec_res.latency_ms,
            executed_at=datetime.now(timezone.utc) if exec_res.success else None,
        )
        self.db.add(order)
        if exec_res.success:
            # 更新虚拟账本锁定
            if sig.action == "open":
                bot.virtual_locked_usdt = bot.virtual_locked_usdt + margin
            elif sig.action == "close":
                bot.virtual_locked_usdt = 0.0
            await self._sync_position(bot, sig, exec_res)
        await self.db.commit()
        await self.db.refresh(order)
        # ★ M6 P0：实时推送下单结果 + 仓位变化
        from api.ws.hub import hub

        await hub.push(
            bot.user_id,
            "bot.order",
            {
                "order_id": order.id,
                "bot_id": bot.id,
                "strategy_id": bot.strategy_id,
                "action": order.action,
                "symbol": sig.symbol,
                "qty": order.qty,
                "status": order.status,
                "failure_category": order.failure_category,
                "latency_ms": order.latency_ms,
            },
        )
        await hub.push(
            bot.user_id,
            "bot.position",
            {
                "bot_id": bot.id,
                "symbol": sig.symbol,
                "action": sig.action,
                "virtual_locked_usdt": bot.virtual_locked_usdt,
            },
        )
        return order

    async def _sync_position(self, bot: CopyBot, sig: SourceSignal, exec_res: ExecResult) -> None:
        """T3.7 TradeTracker 简化版：更新 PositionSnapshot。"""
        existing = (
            await self.db.execute(
                select(PositionSnapshot).where(
                    PositionSnapshot.bot_id == bot.id,
                    PositionSnapshot.symbol == sig.symbol,
                    PositionSnapshot.is_open == True,  # noqa: E712
                )
            )
        ).scalars().first()
        if sig.action == "close":
            if existing:
                existing.is_open = False
            return
        if existing:
            existing.qty += exec_res.filled_qty
            existing.mark_price = exec_res.avg_price or existing.mark_price
            existing.notional_usdt = existing.qty * exec_res.avg_price
            existing.unrealized_pnl = 0.0
        else:
            self.db.add(
                PositionSnapshot(
                    bot_id=bot.id, symbol=sig.symbol, side=sig.side,
                    qty=exec_res.filled_qty, entry_price=exec_res.avg_price,
                    mark_price=exec_res.avg_price, notional_usdt=exec_res.filled_qty * exec_res.avg_price,
                    is_open=True,
                )
            )

    async def _get_contract(self, exchange: str, symbol: str) -> Contract | None:
        row = (
            await self.db.execute(
                select(ContractSpec).where(ContractSpec.exchange == exchange, ContractSpec.symbol == symbol)
            )
        ).scalars().first()
        if row is None:
            # ★ G08 回退兜底：adapter.fetch_contract_spec
            try:
                adapter = get_adapter(exchange)
                spec = await adapter.fetch_contract_spec(symbol)
                return Contract(exchange=exchange, symbol=symbol, **spec)
            except Exception:
                return None
        return Contract(
            exchange=row.exchange, symbol=row.symbol,
            face_value_usdt=row.face_value_usdt, min_size=row.min_size,
            size_precision=row.size_precision,
        )

    async def _get_free_balance(self, bot, api_row, api_secret: str) -> float:
        if getattr(bot, "paper", False):
            from api.services.paperbroker.service import PaperBroker

            return await PaperBroker(self.db).get_free_balance(bot.id)
        adapter = get_adapter(bot.exchange)
        items = await adapter.fetch_balance(api_row.api_key, api_secret)
        for item in items:
            if item.asset == "USDT":
                return item.free
        return 0.0

    async def _current_position(self, bot, api_row, api_secret, symbol: str) -> dict | None:
        """查询持仓：paper 走虚拟快照，真实走交易所；mock 返回 size 字段 → 归一化为 qty。"""
        if getattr(bot, "paper", False):
            from api.services.paperbroker.service import PaperBroker

            return await PaperBroker(self.db).get_position(bot.id, symbol)
        adapter = get_adapter(bot.exchange)
        key = getattr(api_row, "api_key", None) or ""
        pos = await adapter.get_position(symbol, key, api_secret)
        if pos is not None and "qty" not in pos and "size" in pos:
            pos["qty"] = abs(float(pos["size"]))
        return pos

    async def _execute_order(
        self, *, bot, sig, side: str, qty: float, leverage: int, margin_mode: str, reduce_only: bool,
        api_key: str = "", api_secret: str = "",
    ) -> ExecResult:
        """★ M6 T6.2：paper bot 走 PaperBroker 模拟撮合，否则真实交易所。"""
        if getattr(bot, "paper", False):
            from api.services.paperbroker.service import PaperBroker

            return await PaperBroker(self.db).execute(
                bot=bot, symbol=sig.symbol, side=side, qty=qty,
                leverage=leverage, margin_mode=margin_mode,
                reduce_only=reduce_only, signal_price=getattr(sig, "_price", None),
            )
        return await self.router.execute(
            exchange=bot.exchange,
            symbol=sig.symbol,
            side=side,
            qty=qty,
            leverage=leverage,
            margin_mode=margin_mode,
            reduce_only=reduce_only,
            signal_price=getattr(sig, "_price", None),
            api_key=api_key,
            api_secret=api_secret,
        )

    async def _subscription_active(self, user_id: int) -> bool:
        """★ G10 + M5 T5.10：真实订阅校验（active 且未过期）。"""
        from api.services.billing.service import BillingService

        try:
            sub = await BillingService(self.db).get_active_subscription(user_id)
            return sub is not None
        except Exception:  # noqa: BLE001
            return True
