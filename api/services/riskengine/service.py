# 风控引擎（M3 T3.5：5 条规则短路评估 + ★G10 订阅过期拦截）
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from api.core.config import get_settings
from api.services.settings import service as settings_svc


class RiskDecision(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class RiskResult:
    decision: RiskDecision
    rule: str | None = None
    reason: str = ""
    latency_ms: int = 0

    @property
    def approved(self) -> bool:
        return self.decision == RiskDecision.APPROVED

    @property
    def rejected(self) -> bool:
        return self.decision == RiskDecision.REJECTED


@dataclass
class OrderIntent:
    """风控评估的意图上下文。"""

    user_id: int
    bot_id: int
    strategy_id: int
    exchange: str
    symbol: str
    action: str            # open / add / reduce / close（★ G03）
    margin_usdt: float
    signal_received_at: datetime
    source_mode: str = "A"
    # 上下文（由调用方注入）
    subscription_active: bool = True
    identity_type: str = "normal"
    bot_virtual_locked: float = 0.0
    bot_max_total_position: float = 10_000.0
    global_concurrent_now: int = 0
    today_realized_pnl: float = 0.0
    daily_loss_limit: float = -1_000.0
    emergency_stop: bool = False
    strategy_whitelisted: bool = True
    extra: dict = field(default_factory=dict)


class RiskEngine:
    """5 条风控规则，短路评估（第一条命中即终止）：

    1. whitelist     策略是否允许跟单
    2. position_limit 单机器人名义上限（virtual_locked + margin ≤ max）
    3. concurrency   全局并发订单节流
    4. daily_loss    当日已实现亏损上限
    5. emergency_stop 全局紧急制动
    ★ G10 前置：订阅过期拦截 OPEN/ADD，放行 REDUCE/CLOSE
    ★ 延迟红线：模式 A >10s / 模式 B >5s 拒绝
    ★ G03：action 合法性校验
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._hooks: list[Callable[[OrderIntent], None]] = []

    def register_hook(self, hook: Callable[[OrderIntent], None]) -> None:
        """注册评估前钩子（如从 DB 加载实时上下文）。"""
        self._hooks.append(hook)

    async def _run_hooks(self, intent: OrderIntent) -> None:
        for hook in self._hooks:
            result = hook(intent)
            if asyncio.iscoroutine(result):
                await result

    async def evaluate(self, intent: OrderIntent) -> RiskResult:
        start = datetime.now(timezone.utc)
        await self._run_hooks(intent)

        # ★ M6 T6.2：风控决策监控打点
        from api.core import metrics as M

        def _decide(decision, **kw):
            M.risk_decisions_total.labels(decision=decision.value).inc()
            if decision == RiskDecision.REJECTED:
                kw.setdefault("latency_ms", int((datetime.now(timezone.utc) - start).total_seconds() * 1000))
            return RiskResult(decision, **kw)

        # ★ G03：action 合法性
        if intent.action not in ("open", "add", "reduce", "close"):
            return _decide(RiskDecision.REJECTED, rule="action", reason=f"unknown action: {intent.action}")

        # ★ G10：订阅过期拦截 OPEN/ADD，放行 REDUCE/CLOSE
        if not intent.subscription_active and intent.identity_type != "sub_account":
            if intent.action in ("open", "add"):
                return _decide(
                    RiskDecision.REJECTED, rule="subscription",
                    reason="subscription expired, open/add blocked",
                )

        # 1. 策略白名单
        if not intent.strategy_whitelisted:
            return _decide(RiskDecision.REJECTED, rule="whitelist", reason="strategy not whitelisted")

        # 2. 机器人名义上限（后台「风控中心」notional_limit 全局封顶，二者取小）
        global_cap = settings_svc.risk_rule_float("notional_limit", 10_000.0)
        eff_cap = min(intent.bot_max_total_position, global_cap)
        if intent.bot_virtual_locked + intent.margin_usdt > eff_cap:
            return _decide(
                RiskDecision.REJECTED, rule="position_limit",
                reason=f"bot cap: locked {intent.bot_virtual_locked:.2f} + margin {intent.margin_usdt:.2f} > max {eff_cap:.2f}",
            )

        # 3. 全局并发节流
        max_concurrent = self.settings.risk_max_concurrent if hasattr(self.settings, "risk_max_concurrent") else 50
        if intent.global_concurrent_now >= max_concurrent:
            return _decide(
                RiskDecision.REJECTED, rule="concurrency",
                reason=f"global throttle: {intent.global_concurrent_now} >= {max_concurrent}",
            )

        # ★ 延迟红线：模式 A >10s / 模式 B >5s（后台「风控中心」delay_red_line_a/b 可配置，秒单位）
        # ★ close/reduce（风险释放动作）豁免延迟规则（2026-08-20，与 signalstore 红线豁免
        #   口径一致）：迟到开仓是追价风险该拒；迟到平仓仍是风险释放——若开仓已跟单
        #   而平仓被延迟规则拒绝（消费队列积压/received_at 距今超阈值），
        #   bot 持仓将无人关闭（无界敞口）。其余规则（亏损上限/紧急制动等）不豁免。
        age_ms = (datetime.now(timezone.utc) - intent.signal_received_at).total_seconds() * 1000
        delay_a_s = settings_svc.risk_rule_float("delay_red_line_a", self.settings.delay_redline_mode_a_ms / 1000.0)
        delay_b_s = settings_svc.risk_rule_float("delay_red_line_b", self.settings.delay_redline_mode_b_ms / 1000.0)
        if intent.action not in ("close", "reduce"):
            if intent.source_mode == "A" and age_ms > delay_a_s * 1000:
                return _decide(RiskDecision.REJECTED, rule="delay", reason=f"mode A age {age_ms:.0f}ms > {delay_a_s:g}s")
            if intent.source_mode == "B" and age_ms > delay_b_s * 1000:
                return _decide(RiskDecision.REJECTED, rule="delay", reason=f"mode B age {age_ms:.0f}ms > {delay_b_s:g}s")

        # 4. 当日亏损上限
        if intent.today_realized_pnl < intent.daily_loss_limit:
            return _decide(
                RiskDecision.REJECTED, rule="daily_loss",
                reason=f"daily loss {intent.today_realized_pnl:.2f} < limit {intent.daily_loss_limit:.2f}",
            )

        # 5. 紧急制动
        if intent.emergency_stop:
            return _decide(RiskDecision.REJECTED, rule="emergency_stop", reason="emergency stop engaged")

        latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        return _decide(RiskDecision.APPROVED, latency_ms=latency)
