# -*- coding: utf-8 -*-
"""调试：检查 detail 接口 profit 对象原始字段格式（profit_rate 是比例还是百分数）。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main():
    from api.services.scraper.adapters.gate import GateScraper

    scraper = GateScraper()
    try:
        for lid in ["6459", "29274", "22425", "30853"]:
            # 直接调用底层 _api 拿原始响应
            resp = await scraper._api(
                "/api/copytrade/copy_trading/trader/detail/{lid}".format(lid=lid),
                {"sub_website_id": 0},
            )
            if not resp or resp.get("code") != 200:
                print(f"=== {lid}: 接口异常 {str(resp)[:120]}")
                continue
            data = resp.get("data") or {}
            profit = data.get("profit") or {}
            print(f"=== leader {lid} profit 全部字段 ===")
            print(json.dumps(profit, ensure_ascii=False, indent=1)[:2000])
            await asyncio.sleep(3)
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
