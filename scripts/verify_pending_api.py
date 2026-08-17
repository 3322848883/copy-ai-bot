# -*- coding: utf-8 -*-
"""查询 admin 用户 id 并验证待选池 API。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import text


async def main():
    from api.core.security import create_token
    from api.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        r = await db.execute(text("SELECT id, email, role FROM users WHERE role='admin' ORDER BY id LIMIT 3"))
        admins = [dict(row._mapping) for row in r]
    print("admins:", admins)
    if not admins:
        return
    admin_id = admins[0]["id"]
    token = create_token(subject=str(admin_id), audience="admin", extra={"role": "admin"})
    async with httpx.AsyncClient(trust_env=False, base_url="http://127.0.0.1:8000") as c:
        r = await c.get("/admin/v1/signals/pending", params={"exchange": "gate"},
                        headers={"Authorization": f"Bearer {token}"})
        print("status:", r.status_code)
        if r.status_code != 200:
            print(r.text[:300])
            return
        data = r.json()
        items = data.get("items", [])
        print(f"待选池共 {len(items)} 条，前 8 条：")
        for it in items[:8]:
            print(
                f"  {it['name']:<16} roi7={it['roi_7d']:<7} roi30={it['roi_30d']:<7} "
                f"roi_all={it['roi_all']:<9} wr={it['win_rate_all']:<6} dd={it['max_drawdown']:<6} "
                f"days={it['trading_days']:<4} fol={it['followers']}"
            )
        for it in items:
            if it["trader_id"] == "6459":
                print("\n6459:", json.dumps(it, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
