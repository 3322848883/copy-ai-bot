# -*- coding: utf-8 -*-
"""验证 _to_raw_trader 与 get_leader_by_id 的字段映射修复。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.services.scraper.adapters.gate import GateScraper


def test_to_raw_trader():
    """排行榜接口 cycle=month 数据：只填 30d 字段，其他周期留 0。"""
    it = {
        "leader_id": 6459,
        "user_info": {"nick": "老衲要囤币pro"},
        "curr_follow_num": 132,
        "profit_rate": "0.0179",   # 月收益 1.79%
        "win_rate": "0.9636",      # 月胜率 96.36%
        "max_drawdown": "0.007",   # 月回撤 0.7%
        "leading_days": 686,
    }
    t = GateScraper._to_raw_trader(it)
    print("=== _to_raw_trader ===")
    print(f"  followers      = {t.followers}  (期望 132)")
    print(f"  roi_7d         = {t.roi_7d}  (期望 0，由 week/detail 补拉)")
    print(f"  roi_30d        = {t.roi_30d}  (期望 1.79)")
    print(f"  roi_90d        = {t.roi_90d}  (期望 0)")
    print(f"  roi_all        = {t.roi_all}  (期望 0)")
    print(f"  win_rate_30d   = {t.win_rate_30d}  (期望 96.36)")
    print(f"  win_rate_all   = {t.win_rate_all}  (期望 0)")
    print(f"  max_drawdown   = {t.max_drawdown}  (期望 0.7)")
    print(f"  trading_days   = {t.trading_days}  (期望 686)")
    assert t.followers == 132
    assert t.roi_7d == 0 and t.roi_90d == 0 and t.roi_all == 0
    assert t.roi_30d == 1.79
    assert t.win_rate_30d == 96.36
    assert t.win_rate_all == 0
    assert abs(t.max_drawdown - 0.7) < 1e-9
    assert t.trading_days == 686
    print("  PASS")


def test_get_leader_by_id_mapping():
    """详情接口数据：profit_rate 已是百分数，各周期字段是小数。"""
    # 模拟 get_leader_by_id 内部解析逻辑
    profit = {
        "profit_rate": "19.2808",          # 全周期累计收益率（已是百分数 19.28%）
        "seven_profit_rate": "0.008",      # 7天收益率（小数 0.8%）
        "month_profit_rate": "0.0179",     # 月收益率（小数 1.79%）
        "three_month_profit_rate": "0.3756",  # 3月收益率（小数 37.56%）
        "win_num": 684,
        "loss_num": 85,
        "month_win_rate": "0.9636",        # 月胜率（小数 96.36%）
        "max_drawdown": "0.0455",          # 全周期回撤（小数 4.55%）
        "curr_follow_num": 132,
        "duration_day": 686,
    }
    win_num = profit.get("win_num") or 0
    loss_num = profit.get("loss_num") or 0
    total = win_num + loss_num
    mapping = {
        "roi_7d": GateScraper._to_pct(profit.get("seven_profit_rate")),
        "roi_30d": GateScraper._to_pct(profit.get("month_profit_rate")),
        "roi_90d": GateScraper._to_pct(profit.get("three_month_profit_rate")),
        "roi_all": float(profit.get("profit_rate") or 0),
        "win_rate_30d": GateScraper._to_pct(profit.get("month_win_rate")),
        "win_rate_all": round(win_num / total * 100, 1) if total else 0.0,
        "max_drawdown": GateScraper._to_pct(profit.get("max_drawdown")),
        "followers": profit.get("curr_follow_num") or 0,
        "trading_days": int(profit.get("duration_day") or 0),
    }
    print("\n=== get_leader_by_id 字段映射 ===")
    for k, v in mapping.items():
        print(f"  {k} = {v}")
    assert mapping["roi_7d"] == 0.8
    assert mapping["roi_30d"] == 1.79
    assert mapping["roi_90d"] == 37.56
    assert mapping["roi_all"] == 19.2808
    assert mapping["win_rate_30d"] == 96.36
    assert mapping["win_rate_all"] == round(684 / 769 * 100, 1)  # 88.9
    assert mapping["max_drawdown"] == 4.55
    assert mapping["followers"] == 132
    assert mapping["trading_days"] == 686
    print("  PASS")


if __name__ == "__main__":
    test_to_raw_trader()
    test_get_leader_by_id_mapping()
    print("\nALL PASS")
