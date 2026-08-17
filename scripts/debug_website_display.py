# -*- coding: utf-8 -*-
"""调试：官网详情页切换「全部」周期，读取累计简单收益率/带单收益率。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main():
    from api.services.scraper.adapters.gate import GATE_BASE, GateScraper

    scraper = GateScraper()
    try:
        await scraper._ensure_browser()
        page = scraper._pages[0]
        for lid in ["6459", "29274"]:
            url = f"{GATE_BASE}/zh/copytrading/trader/futures/{lid}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(6000)
                # 尝试点击「全部」周期按钮
                clicked = False
                for label in ["全部", "总览", "累计"]:
                    try:
                        btn = page.get_by_text(label, exact=True).first
                        await btn.click(timeout=3000)
                        await page.wait_for_timeout(2500)
                        clicked = True
                        print(f"=== {lid} 点击了「{label}」 ===")
                        break
                    except Exception:  # noqa: BLE001
                        continue
                text = await page.inner_text("body")
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                print(f"=== leader {lid} 页面文本(含收益/胜率/回撤) ===")
                for i, l in enumerate(lines):
                    if any(k in l for k in ["%", "收益", "胜率", "回撤", "盈亏"]):
                        print("   ", l)
            except Exception as exc:  # noqa: BLE001
                print(f"=== {lid} 页面抓取失败: {exc}")
            await asyncio.sleep(3)
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
