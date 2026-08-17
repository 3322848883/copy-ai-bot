# -*- coding: utf-8 -*-
"""用实测的 detail 接口数据更新 6459 画像快照，验证修复后的字段映射。

6459 detail 接口实测数据（2026-08-17）：
  profit_rate=19.2808(比例值，×100=1928.08% 累计带单收益率)  seven_profit_rate=0.008  month_profit_rate=0.0179
  three_month_profit_rate=0.3756  win_num=684 loss_num=85  month_win_rate=0.9636
  max_drawdown=0.0455  curr_follow_num=132  duration_day=686
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text


async def main():
    from api.db.session import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        # 6459 的 traders id
        r = await db.execute(text("SELECT id, followers FROM traders WHERE trader_id='6459'"))
        row = r.first()
        if not row:
            print("6459 not found")
            return
        tid = row[0]
        print(f"trader id={tid}, old followers={row[1]}")

        # 删除旧画像快照
        await db.execute(text("DELETE FROM trader_profiles WHERE trader_id=:tid"), {"tid": tid})
        # 写入新快照（修复后字段映射）
        await db.execute(
            text(
                "INSERT INTO trader_profiles "
                "(trader_id, snapshot_date, roi_7d, roi_30d, roi_90d, roi_all, "
                "win_rate_30d, win_rate_all, max_drawdown, trading_days) "
                "VALUES (:tid, CURRENT_DATE, :r7, :r30, :r90, :ra, :w30, :wa, :dd, :days)"
            ),
            {
                "tid": tid,
                "r7": 0.8,        # seven_profit_rate 0.008 * 100
                "r30": 1.79,      # month_profit_rate 0.0179 * 100
                "r90": 37.56,     # three_month_profit_rate 0.3756 * 100
                "ra": 1928.08,    # profit_rate 是比例值，×100 = 1928.08% 累计带单收益率
                "w30": 96.36,     # month_win_rate 0.9636 * 100
                "wa": round(684 / 769 * 100, 1),  # 88.9
                "dd": 4.55,       # max_drawdown 0.0455 * 100
                "days": 686,      # duration_day
            },
        )
        # 更新 traders.followers 为真实跟单人数
        await db.execute(
            text("UPDATE traders SET followers=132 WHERE id=:tid"), {"tid": tid}
        )
        await db.commit()

        # 验证
        r = await db.execute(
            text(
                "SELECT p.snapshot_date, p.roi_7d, p.roi_30d, p.roi_90d, p.roi_all, "
                "p.win_rate_30d, p.win_rate_all, p.max_drawdown, p.trading_days, t.followers "
                "FROM trader_profiles p JOIN traders t ON p.trader_id=t.id "
                "WHERE t.trader_id='6459'"
            )
        )
        for row in r:
            print("UPDATED PROFILE:", dict(row._mapping))


if __name__ == "__main__":
    asyncio.run(main())
