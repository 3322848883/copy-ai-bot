"""Seed 完整测试数据：策略 / 画像快照(90天净值曲线) / 机器人 / 订单 / 持仓 / 订阅 / 邀请 / 奖励 / API Key。"""
import asyncio
import os
import sys
import math
import random
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///c:/Users/w6485/Desktop/AI 量化/信号聚合AI/dev.db"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from api.models import (
    Trader, TraderProfile, Strategy, CopyBot, CopyOrder, PositionSnapshot,
    Subscription, Invite, Reward, PaymentOrder, ApiKey,
)
from api.core.security import ApiKeyVault

DB = "c:/Users/w6485/Desktop/AI 量化/信号聚合AI/dev.db"
random.seed(42)


def _equity_curve(days: int, target_roi: float, seed: int) -> list[float]:
    """确定性生成一条平滑累计净值曲线（%），从 0 平滑爬到 target_roi。"""
    rnd = random.Random(seed)
    pts = []
    val = 0.0
    for i in range(days):
        progress = (i + 1) / days
        # 目标附近 + 随机游走，保证末点 ≈ target
        drift = target_roi * 0.02
        val += drift + rnd.uniform(-0.15, 0.2)
        # 平滑：向目标均值靠拢
        val = val * 0.92 + (target_roi * progress) * 0.08
        pts.append(round(val, 2))
    pts[-1] = round(target_roi, 2)
    return pts


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        today = date.today()

        # ── 1. 带单员 + 策略（3 个）──
        specs = [
            # (trader_id, name, followers, display, style, risk, win_rate, drawdown, days, roi_all, roi_30d)
            ("slow_bull_32801", "慢牛信号", 328, "趋势猎手·慢牛", "trend", "mid", 62.5, 18.2, 120, 86.4, 21.3),
            ("wind_keys_24264", "风控大师", 214, "风控稳健·波段", "range", "low", 70.1, 12.4, 200, 54.2, 9.8),
            ("alpha_engine_9", "Alpha引擎", 501, "Alpha动量·进攻", "momentum", "high", 58.9, 27.6, 90, 132.5, 35.7),
        ]
        traders = {}
        strategies = {}
        for i, (tid, name, followers, display, style, risk, wr, dd, days, roi_all, roi_30d) in enumerate(specs, start=1):
            t = Trader(id=i, exchange="gate", trader_id=tid, name=name, followers=followers)
            db.add(t)
            await db.flush()
            traders[tid] = t
            s = Strategy(
                trader_id=t.id, source_exchange="gate", display_name=display,
                style=style, risk_rating=risk, gray_pct=100, status="listed",
            )
            db.add(s)
            await db.flush()
            strategies[tid] = s

            # ── 每日画像快照（90 天，构成净值曲线）──
            curve = _equity_curve(90, roi_all, seed=i)
            for d in range(90):
                sd = today - timedelta(days=89 - d)
                # 累积 roi_all = curve[d]；roi_30d ≈ 近 30 天累计
                p = TraderProfile(
                    trader_id=t.id, snapshot_date=sd,
                    roi_7d=round(curve[d] - curve[max(0, d - 7)], 1),
                    roi_30d=round(curve[d] - curve[max(0, d - 30)], 1),
                    roi_90d=round(curve[d], 1),
                    roi_all=round(curve[d], 1),
                    win_rate_30d=round(wr + random.uniform(-3, 3), 1),
                    win_rate_all=wr,
                    max_drawdown=dd,
                    trading_days=days,
                )
                db.add(p)
        await db.flush()

        # ── 2. API Key（用户 10000 绑定 gate）──
        vault = ApiKeyVault("0123456789abcdef" * 4)
        ct, nonce, tag, aad = vault.encrypt("dummy-key", "10000|gate")
        ak = ApiKey(user_id=10000, exchange="gate", ciphertext=ct, nonce=nonce, tag=tag, aad=aad, status="active")
        db.add(ak)
        await db.flush()

        # ── 3. 订阅（用户 10000 有效月卡）──
        sub = Subscription(
            user_id=10000, plan_id="monthly_19_9u", status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(sub)

        # ── 4. 机器人（用户 10000）──
        bot = CopyBot(
            user_id=10000, strategy_id=strategies["slow_bull_32801"].id,
            exchange="gate", api_key_id=ak.id, amount_mode="percent", percent=20.0,
            leverage=10, margin_mode="isolated", max_total_position_usdt=10000,
            virtual_locked_usdt=1200, status="active", paper=False,
        )
        db.add(bot)
        await db.flush()

        # ── 5. 持仓 + 订单（供详情展开）──
        db.add(PositionSnapshot(
            bot_id=bot.id, symbol="ETHUSDT", side="long", qty=0.5, entry_price=3200,
            mark_price=3350, unrealized_pnl=75.0, notional_usdt=1675, is_open=True,
        ))
        for act, status, cat, latency in [
            ("open", "filled", None, 320), ("open", "filled", None, 290),
            ("close", "filled", None, 305), ("open", "failed", "balance", None),
        ]:
            db.add(CopyOrder(
                bot_id=bot.id, signal_id=1, action=act, qty=0.5, leverage=10,
                required_margin_usdt=160, status=status, failure_category=cat,
                latency_ms=latency, executed_at=datetime.now(timezone.utc) if status == "filled" else None,
            ))

        # ── 6. 邀请 + 奖励（用户 10002/10003 被 9999 邀请）──
        for i, (invitee_id, amt, rstatus) in enumerate([(10002, 1.99, "available"), (10003, 1.99, "verifying")]):
            now = datetime.now(timezone.utc)
            po = PaymentOrder(user_id=invitee_id, plan_id="monthly_19_9u", amount_usdt=19.9, network="trc20", status="confirmed")
            db.add(po)
            await db.flush()
            db.add(Invite(inviter_id=9999, invitee_id=invitee_id, code="FRIEND-A", bound_at=now - timedelta(days=i), locked=False))
            db.add(Reward(
                owner_id=9999, source_user_id=invitee_id, source_payment_order_id=po.id,
                amount_usdt=amt, status=rstatus,
                verifying_started_at=now - timedelta(days=i),
                verifying_ends_at=(now + timedelta(hours=24)) if rstatus == "verifying" else None,
            ))

        await db.commit()

    # ── 统计 ──
    async with engine.connect() as conn:
        from sqlalchemy import text
        for t in ["traders", "trader_profiles", "strategies", "copy_bots", "copy_orders", "position_snapshots", "subscriptions", "invites", "rewards", "api_keys"]:
            n = (await conn.execute(text(f"select count(*) from {t}"))).scalar()
            print(f"{t}: {n}")
    await engine.dispose()
    print("SEED OK")


asyncio.run(main())