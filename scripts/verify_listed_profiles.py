# -*- coding: utf-8 -*-
"""验证已上架策略的带单员画像数据（修复后字段映射）。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text


async def main():
    from api.db.session import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        r = await db.execute(text(
            """
            SELECT t.trader_id, t.name, t.followers, p.snapshot_date,
                   p.roi_7d, p.roi_30d, p.roi_90d, p.roi_all,
                   p.win_rate_30d, p.win_rate_all, p.max_drawdown, p.trading_days
            FROM traders t
            JOIN strategies s ON s.trader_id = t.id
            LEFT JOIN LATERAL (
                SELECT * FROM trader_profiles
                WHERE trader_id = t.id
                ORDER BY snapshot_date DESC LIMIT 1
            ) p ON true
            WHERE s.status = 'listed'
            ORDER BY t.id
            """
        ))
        rows = r.all()
        if not rows:
            print("NO LISTED STRATEGIES")
            return
        print(f"{'trader_id':<9} {'name':<14} {'fol':<5} {'snapshot':<12} "
              f"{'roi7':<7} {'roi30':<7} {'roi90':<8} {'roi_all':<9} "
              f"{'wr30':<7} {'wr_all':<7} {'dd':<7} {'days'}")
        for row in rows:
            tid, name, fol, snap, r7, r30, r90, ra, w30, wa, dd, days = row
            print(f"{str(tid):<9} {(name or '')[:12]:<14} {str(fol):<5} {str(snap):<12} "
                  f"{str(r7):<7} {str(r30):<7} {str(r90):<8} {str(ra):<9} "
                  f"{str(w30):<7} {str(wa):<7} {str(dd):<7} {days}")


if __name__ == "__main__":
    asyncio.run(main())
