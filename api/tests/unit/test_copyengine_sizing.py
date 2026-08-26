# CopyEngine qty 换算（percent×保证金）与测试符号过滤 单元测试
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import MethodType
from types import SimpleNamespace

from api.services.copyengine.service import CopyEngine
from api.services.scraper.adapters.gate import GateScraper
from api.workers.tasks_signal import _is_test_symbol


def _bot(percent: float = 10.0) -> SimpleNamespace:
    return SimpleNamespace(percent=percent)


def _sig(action: str = "open", percent: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(action=action, percent=percent)


# ── qty 换算：_effective_percent ──
def test_open_scales_by_leader_percent():
    """open 信号带 leader 占比 → 下单比例 = bot.percent × leader_percent。"""
    # bot 10%，leader 20% → 2%
    assert CopyEngine._effective_percent(_bot(10.0), _sig("open", 0.20)) == 2.0


def test_open_without_percent_keeps_bot_percent():
    """批量/WS 信号无占比(None) → 用 bot.percent（原行为）。"""
    assert CopyEngine._effective_percent(_bot(10.0), _sig("open", None)) == 10.0


def test_add_action_scales_by_position_increase_ratio():
    """带单员仓位增加 20% 时，本账户也按原配置比例的 20% 加仓。"""
    assert CopyEngine._effective_percent(_bot(10.0), _sig("add", 0.20)) == 2.0


def test_leader_percent_clamped_to_unit_interval():
    """leader 占比截断到 [0,1]：>1 按 1，<0 按 0。"""
    assert CopyEngine._effective_percent(_bot(10.0), _sig("open", 2.0)) == 10.0
    assert CopyEngine._effective_percent(_bot(10.0), _sig("open", -0.5)) == 0.0


def test_leader_percent_non_numeric_fallback():
    """leader 占比非数字 → 回退 bot.percent。"""
    assert CopyEngine._effective_percent(_bot(10.0), _sig("open", "bad")) == 10.0


def test_fixed_amount_is_same_margin_for_open_and_add_orders():
    bot = SimpleNamespace(fixed_amount_usdt=100.0)
    assert CopyEngine._effective_fixed_amount(bot, _sig("add", 0.20)) == 100.0
    assert CopyEngine._effective_fixed_amount(bot, _sig("open", 0.20)) == 100.0


def test_open_risk_timestamp_uses_source_time_not_detection_time():
    """晚发现的旧仓位必须保留源时间，才能被 5s/10s 延迟红线拒绝追单。"""
    received = datetime.now(timezone.utc)
    opened = received - timedelta(minutes=95)
    sig = SimpleNamespace(action="open", opened_at=opened, received_at=received)
    assert CopyEngine._risk_timestamp(sig) == opened


def test_close_risk_timestamp_uses_received_time():
    received = datetime.now(timezone.utc)
    opened = received - timedelta(hours=2)
    sig = SimpleNamespace(action="close", opened_at=opened, received_at=received)
    assert CopyEngine._risk_timestamp(sig) == received


# ── 测试符号过滤 ──
def test_gate_scraper_is_test_symbol():
    """Gate 适配器：测试符号标记命中。"""
    assert GateScraper._is_test_symbol("TESTUSDT") is True
    assert GateScraper._is_test_symbol("BTCUSDT") is False
    assert GateScraper._is_test_symbol("btcusdt") is False  # 大小写不敏感但非测试
    assert GateScraper._is_test_symbol("DEMOUSDT") is True


def test_worker_is_test_symbol():
    """Celery 任务层兜底过滤。"""
    assert _is_test_symbol("TESTUSDT") is True
    assert _is_test_symbol("ETHUSDT") is False


# ── 无头可配置 ──
def test_headless_args_headful_empty():
    """有头模式：无额外启动参数。"""
    assert GateScraper._headless_args(False, "new") == []


def test_headless_args_new_mode():
    """无头 new 模式：--headless=new（指纹难区分）。"""
    assert GateScraper._headless_args(True, "new") == ["--headless=new"]


def test_headless_args_old_mode():
    """无头 old 模式：--headless=old。"""
    assert GateScraper._headless_args(True, "old") == ["--headless=old"]


# ── 灰度放量哈希稳定性（M6 P1 修复）──
def test_gray_allowed_boundaries():
    """灰度边界：100 全量、0 全拦、中间按比例。"""
    assert CopyEngine._gray_allowed(1, 1, 100) is True
    assert CopyEngine._gray_allowed(1, 1, 0) is False


def test_gray_allowed_deterministic_across_calls():
    """同一用户/策略/比例 → 结果恒定（跨进程稳定）。"""
    a = CopyEngine._gray_allowed(42, 7, 30)
    b = CopyEngine._gray_allowed(42, 7, 30)
    assert a == b


def test_gray_allowed_distribution_roughly_correct():
    """100 个用户放量 30% → 命中数接近 30（±8）。"""
    hits = sum(CopyEngine._gray_allowed(1, uid, 30) for uid in range(100))
    assert 22 <= hits <= 38, f"灰度命中偏离过大: {hits}"


def test_handle_signal_isolates_one_bot_unhandled_failure():
    """一个 API/网络异常必须落失败单，并继续处理同信号下的其他机器人。"""
    class FakeDb:
        def __init__(self):
            self.added = []
            self.commits = 0

        def add(self, value):
            self.added.append(value)

        async def commit(self):
            self.commits += 1

        async def scalar(self, statement):
            return None

    engine = object.__new__(CopyEngine)
    engine.db = FakeDb()
    bots = [
        SimpleNamespace(id=1, user_id=10, strategy_id=100, leverage=5),
        SimpleNamespace(id=2, user_id=20, strategy_id=100, leverage=5),
    ]

    async def fake_match(self, exchange, trader_id):
        return bots

    async def fake_process(self, bot, sig):
        if bot.id == 1:
            raise RuntimeError("temporary balance API failure")
        return self._fail_order(bot, sig, "other", "second bot reached")

    engine.match_bots = MethodType(fake_match, engine)
    engine._process_bot = MethodType(fake_process, engine)
    sig = SimpleNamespace(
        id=99, exchange="gate", source_trader_id="32801", symbol="ETHUSDT",
        side="long", action="open", percent=None, source_mode="B",
    )
    orders = asyncio.run(engine.handle_signal(sig))
    assert len(orders) == 2
    assert orders[0].status == "failed"
    assert "temporary balance API failure" in orders[0].fail_reason
    assert orders[1].fail_reason == "second bot reached"
    assert engine.db.commits == 1
