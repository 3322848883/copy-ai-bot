# -*- coding: utf-8 -*-
"""全量刷新所有 gate 带单员画像快照（修复字段复制 bug 后重新采集）。

- 遍历 traders 表中所有 gate 带单员
- 逐个调用 get_leader_by_id（detail 接口）补全多周期画像
- 更新跟单人数（真实 curr_follow_num）
- 覆盖写入今日 TraderProfile 快照（旧 bug 快照被替换）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text


async def main():
    from api.db.session import get_session_factory
    from api.models.signal import Trader, TraderProfile
    from api.services.scraper.adapters.gate import GateScraper
    from api.services.signalstore.service import SignalStore

    factory = get_session_factory()
    async with factory() as db:
        store = SignalStore(db)
        traders = (await db.execute(select(Trader).where(Trader.exchange == "gate"))).scalars().all()
        print(f"共 {len(traders)} 个 gate 带单员，开始采集…")

        # ★ 复用已登录的持久化会话（避免与 Celery worker 争抢同一 user_data_dir 导致 profile 锁冲突）
        from api.services.signal_session.service import get_signal_session

        fetcher = get_signal_session().fetch_api
        scraper = GateScraper()
        ok = fail = 0
        rows = []
        try:
            for t in traders:
                try:
                    detail = await scraper.get_leader_by_id(t.trader_id, fetcher=fetcher)
                except Exception as exc:  # noqa: BLE001
                    print(f"  ✗ {t.trader_id} {t.name} 采集异常: {exc}")
                    fail += 1
                    continue
                if not detail:
                    print(f"  ✗ {t.trader_id} {t.name} detail 接口无数据")
                    fail += 1
                    continue
                # 更新跟单人数（真实 curr_follow_num）
                await store.upsert_trader("gate", t.trader_id, t.name, int(detail.get("followers") or 0))
                # 覆盖今日快照（删除旧快照再插入，避免 uq_trader_profile_date 冲突）
                await db.execute(
                    delete(TraderProfile).where(
                        TraderProfile.trader_id == t.id,
                        TraderProfile.snapshot_date == __import__("datetime").date.today(),
                    )
                )
                db.add(
                    TraderProfile(
                        trader_id=t.id,
                        snapshot_date=__import__("datetime").date.today(),
                        roi_7d=float(detail.get("roi_7d") or 0),
                        roi_30d=float(detail.get("roi_30d") or 0),
                        roi_90d=float(detail.get("roi_90d") or 0),
                        roi_all=float(detail.get("roi_all") or 0),
                        win_rate_30d=float(detail.get("win_rate_30d") or 0),
                        win_rate_all=float(detail.get("win_rate_all") or 0),
                        max_drawdown=float(detail.get("max_drawdown") or 0),
                        trading_days=int(detail.get("trading_days") or 0),
                    )
                )
                await db.flush()
                ok += 1
                rows.append(
                    (t.trader_id, t.name, detail.get("followers"), detail.get("roi_7d"),
                     detail.get("roi_30d"), detail.get("roi_90d"), detail.get("roi_all"),
                     detail.get("win_rate_all"), detail.get("max_drawdown"), detail.get("trading_days"))
                )
                print(f"  ✓ {t.trader_id} {t.name}: 7d={detail.get('roi_7d')} 30d={detail.get('roi_30d')} "
                      f"90d={detail.get('roi_90d')} all={detail.get('roi_all')} wr={detail.get('win_rate_all')} "
                      f"dd={detail.get('max_drawdown')} days={detail.get('trading_days')} fol={detail.get('followers')}")
                await asyncio.sleep(3)  # 反爬间隔
            await db.commit()
        finally:
            await scraper.close()

        print(f"\n完成: 成功 {ok} / 失败 {fail}")
        if rows:
            print(f"{'trader_id':<9} {'name':<16} {'fol':<5} {'roi7':<8} {'roi30':<8} {'roi90':<8} {'roi_all':<9} {'wr_all':<7} {'dd':<7} {'days'}")
            for r in rows:
                tid, name, fol, r7, r30, r90, ra, wa, dd, days = r
                print(f"{str(tid):<9} {(name or '')[:14]:<16} {str(fol):<5} {str(r7):<8} {str(r30):<8} "
                      f"{str(r90):<8} {str(ra):<9} {str(wa):<7} {str(dd):<7} {days}")


if __name__ == "__main__":
    asyncio.run(main())
