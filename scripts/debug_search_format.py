# -*- coding: utf-8 -*-
"""调试：检查 leader/search 接口返回的 profit_rate 格式，交叉验证 detail 接口。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main():
    from api.services.scraper.adapters.gate import GateScraper, LEADER_SEARCH_PATH

    scraper = GateScraper()
    try:
        for name in ["老衲要囤币pro", "挺进2027", "必胜对冲组合量化1"]:
            resp = await scraper._api(
                LEADER_SEARCH_PATH,
                {"name": name, "page": 1, "page_size": 5, "sub_website_id": 0},
            )
            print(f"=== search '{name}' ===")
            if not resp or resp.get("code") != 0:
                print(f"    接口异常: {str(resp)[:120]}")
                await asyncio.sleep(3)
                continue
            for it in (resp.get("data") or {}).get("list") or []:
                keys = ["leader_id", "profit_rate", "simple_profit_rate", "win_rate",
                        "max_drawdown", "curr_follow_num", "leading_days"]
                print("    " + json.dumps({k: it.get(k) for k in keys if k in it}, ensure_ascii=False))
            await asyncio.sleep(3)
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
