# -*- coding: utf-8 -*-
"""最终验证：检查今日快照是否仍存在字段复制 bug（多周期相同但带单>30天）。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text


async def main():
    from api.db.session import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        # 1. 今日快照总数
        r = await db.execute(text(
            "SELECT COUNT(*) FROM trader_profiles WHERE snapshot_date = DATE '2026-08-17'"
        ))
        print(f"今日(本地8/17)快照总数: {r.scalar()}")

        # 2. 疑似字段复制 bug：多周期完全相同 且 带单>30天
        r = await db.execute(text(
            """
            SELECT t.trader_id, t.name, p.trading_days, p.roi_7d, p.roi_30d, p.roi_90d, p.roi_all,
                   p.win_rate_30d, p.win_rate_all
            FROM trader_profiles p JOIN traders t ON p.trader_id=t.id
            WHERE p.snapshot_date = DATE '2026-08-17'
              AND p.trading_days > 30
              AND p.roi_7d = p.roi_30d AND p.roi_30d = p.roi_90d AND p.roi_90d = p.roi_all
            ORDER BY t.trader_id
            """
        ))
        rows = r.all()
        if not rows:
            print("✓ 无字段复制 bug：所有带单>30天的带单员各周期数据已区分")
        else:
            print(f"⚠ 仍有 {len(rows)} 个疑似 bug:")
            for row in rows:
                m = row._mapping
                print(f"  {m['trader_id']:<9} {str(m['name'] or '')[:12]:<14} days={m['trading_days']} "
                      f"7d={m['roi_7d']} 30d={m['roi_30d']} 90d={m['roi_90d']} all={m['roi_all']}")

        # 3. 6459 最终确认
        r = await db.execute(text(
            "SELECT t.trader_id, t.name, t.followers, p.roi_7d, p.roi_30d, p.roi_90d, p.roi_all, "
            "p.win_rate_30d, p.win_rate_all, p.max_drawdown, p.trading_days "
            "FROM trader_profiles p JOIN traders t ON p.trader_id=t.id "
            "WHERE t.trader_id='6459' AND p.snapshot_date = DATE '2026-08-17'"
        ))
        for row in r:
            m = row._mapping
            print(f"\n6459 最终确认: {m['name']} fol={m['followers']} "
                  f"7d={m['roi_7d']}% 30d={m['roi_30d']}% 90d={m['roi_90d']}% "
                  f"all={m['roi_all']}% wr30={m['win_rate_30d']}% wr_all={m['win_rate_all']}% "
                  f"dd={m['max_drawdown']}% days={m['trading_days']}")


if __name__ == "__main__":
    asyncio.run(main())
