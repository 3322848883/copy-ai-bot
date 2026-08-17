"""Additivise 跨交易所演示信号源（仅 INSERT，不清库、不删已有数据）。

把多样化的带单员+策略（Gate 为主 + Binance/OKX 示例）写入当前 DATABASE_URL
（默认取环境变量；prod-local 指向 127.0.0.1:5433 postgres），让策略广场按交易所
展示「不限个数、按所区分」的信号源。已存在同名 trader_id 则跳过（幂等）。

用法：. .\scripts\set-prod-local-env.ps1; python scripts\seed_cross_exchange.py
"""
import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from api.models.signal import Trader, TraderProfile, Strategy

SPECS = [
    # (exchange, trader_id, name, followers, display, style, risk, win_rate, drawdown, days, roi_all, roi_30d)
    ("gate", "slow_bull_32801", "慢牛信号", 328, "趋势猎手·慢牛", "trend", "mid", 62.5, 18.2, 120, 86.4, 21.3),
    ("gate", "wind_keys_24264", "风控大师", 214, "风控稳健·波段", "range", "low", 70.1, 12.4, 200, 54.2, 9.8),
    ("gate", "alpha_engine_9", "Alpha引擎", 501, "Alpha动量·进攻", "momentum", "high", 58.9, 27.6, 90, 132.5, 35.7),
    ("gate", "scalper_x7", "短线快手", 187, "Gate闪电·高频", "range", "high", 56.3, 22.1, 75, 48.3, 7.6),
    ("gate", "gate_rv_6", "RV波动猎人", 146, "Gate波动·反转", "range", "mid", 60.4, 15.7, 140, 67.8, 11.2),
    ("binance", "bn_grid_88", "网格大师", 442, "币安稳健·网格", "range", "mid", 66.3, 14.0, 160, 73.9, 12.4),
    ("binance", "bn_btc_fut", "BTC狙手", 330, "币安BTC·趋势", "trend", "mid", 60.7, 16.8, 130, 91.2, 18.6),
    ("binance", "bn_algo_77", "量化猎手", 258, "币安量化·动量", "momentum", "high", 57.4, 25.9, 85, 118.7, 29.4),
    ("okx", "okx_macd_5", "OKX波段", 196, "OKX波段·MACD", "trend", "low", 68.2, 11.3, 180, 61.5, 8.9),
    ("okx", "okx_hyper_3", "OKX激进", 152, "OKX动量·进攻", "momentum", "high", 55.9, 28.7, 70, 143.8, 38.5),
]


async def main():
    db_url = os.environ.get("DATABASE_URL") or "postgresql+asyncpg://signal:local-test-pg-pass-2026@127.0.0.1:5433/signal_saas"
    engine = create_async_engine(db_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    inserted = skipped = 0
    async with Session() as db:
        for ex, tid, name, followers, display, style, risk, wr, dd, days, roi_all, roi_30d in SPECS:
            exists = await db.scalar(select(Trader).where(Trader.exchange == ex, Trader.trader_id == tid))
            if exists is not None:
                skipped += 1
                continue
            t = Trader(exchange=ex, trader_id=tid, name=name, followers=followers)
            db.add(t)
            await db.flush()
            db.add(Strategy(
                trader_id=t.id, source_exchange=ex, display_name=display,
                style=style, risk_rating=risk, gray_pct=100, status="listed",
            ))
            db.add(TraderProfile(
                trader_id=t.id, snapshot_date=date.today(),
                roi_7d=6.1, roi_30d=roi_30d, roi_90d=roi_all, roi_all=roi_all,
                win_rate_30d=wr - 2.0, win_rate_all=wr,
                max_drawdown=dd, trading_days=days,
            ))
            inserted += 1
        await db.commit()
    await engine.dispose()
    print(f"跨所信号源：新增 {inserted}，跳过(已存在) {skipped}")
    print("SEED CROSS EXCHANGE OK")


asyncio.run(main())