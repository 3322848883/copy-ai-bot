# -*- coding: utf-8 -*-
"""查询待选池所有带单员的画像快照日期与数据来源。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text


async def main():
    from api.db.session import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        r = await db.execute(
            text(
                "SELECT t.id, t.trader_id, t.name, t.followers, "
                "p.snapshot_date, p.roi_7d, p.roi_30d, p.roi_all, p.win_rate_all, p.max_drawdown, p.trading_days "
                "FROM traders t "
                "LEFT JOIN LATERAL (SELECT snapshot_date, roi_7d, roi_30d, roi_all, win_rate_all, max_drawdown, trading_days "
                "  FROM trader_profiles WHERE trader_id=t.id ORDER BY snapshot_date DESC LIMIT 1) p ON true "
                "WHERE t.exchange='gate' ORDER BY p.snapshot_date DESC NULLS LAST"
            )
        )
        print(f"{'id':<5} {'trader_id':<9} {'name':<18} {'fol':<5} {'snap':<12} {'roi7':<8} {'roi30':<8} {'roi_all':<9} {'wr_all':<7} {'dd':<7} {'days'}")
        for row in r:
            tid, trader_id, name, fol, snap, r7, r30, ra, wa, dd, days = row
            print(
                f"{str(tid):<5} {str(trader_id):<9} {(name or '')[:16]:<18} {str(fol):<5} "
                f"{str(snap):<12} {str(r7):<8} {str(r30):<8} {str(ra):<9} {str(wa):<7} {str(dd):<7} {days}"
            )


if __name__ == "__main__":
    asyncio.run(main())
