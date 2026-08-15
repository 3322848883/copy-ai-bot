# CopyEngine qty 换算（percent×保证金）与测试符号过滤 单元测试
from __future__ import annotations

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


def test_add_action_not_scaled():
    """add 动作不缩放，保持 bot.percent。"""
    assert CopyEngine._effective_percent(_bot(10.0), _sig("add", 0.20)) == 10.0


def test_leader_percent_clamped_to_unit_interval():
    """leader 占比截断到 [0,1]：>1 按 1，<0 按 0。"""
    assert CopyEngine._effective_percent(_bot(10.0), _sig("open", 2.0)) == 10.0
    assert CopyEngine._effective_percent(_bot(10.0), _sig("open", -0.5)) == 0.0


def test_leader_percent_non_numeric_fallback():
    """leader 占比非数字 → 回退 bot.percent。"""
    assert CopyEngine._effective_percent(_bot(10.0), _sig("open", "bad")) == 10.0


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