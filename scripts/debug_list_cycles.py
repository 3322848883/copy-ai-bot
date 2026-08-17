# -*- coding: utf-8 -*-
"""调试：检查 leader/list 接口不同 cycle 返回的字段，寻找可靠的累计收益率字段。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main():
    from api.services.scraper.adapters.gate import GateScraper, LEADER_LIST_PATH

    scraper = GateScraper()
    try:
        for cycle in ["month", "week", "all", "total", "three_month"]:
            resp = await scraper._api(
                LEADER_LIST_PATH,
                {"page": 1, "page_size": 5, "status": "running", "order_by": "follow_profit",
                 "sort_by": "desc", "cycle": cycle, "sub_website_id": 0},
            )
            if not resp or resp.get("code") != 0:
                print(f"=== cycle={cycle}: 接口异常 {str(resp)[:100]}")
                continue
            items = resp["data"]["list"]
            if not items:
                print(f"=== cycle={cycle}: 无数据")
                continue
            it = items[0]
            print(f"=== cycle={cycle} 首条字段 ===")
            for k, v in it.items():
                if k in ("user_info", "leader_id", "profit_rate", "win_rate", "max_drawdown",
                         "curr_follow_num", "leading_days", "total_follow_num", "follow_profit"):
                    print(f"    {k} = {v!r}")
            await asyncio.sleep(3)
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
