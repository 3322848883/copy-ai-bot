# -*- coding: utf-8 -*-
"""验证待选池接口 6459 数据。"""
import httpx

c = httpx.Client(timeout=30, trust_env=False)
r = c.post(
    "http://127.0.0.1:8000/admin/v1/auth/login",
    json={"email": "648511672@qq.com", "password": "648511672"},
)
access = r.json().get("access_token")
h = {"Authorization": f"Bearer {access}"}
r = c.get("http://127.0.0.1:8000/admin/v1/signals/pending", headers=h)
items = r.json().get("items", [])
print("PENDING ITEMS:", len(items))
for it in items[:8]:
    print(
        f"  {it['name']:<22} roi7={it['roi_7d']:<7} roi30={it['roi_30d']:<7} "
        f"roi_all={it['roi_all']:<8} wr30={it.get('win_rate_30d', 0):<7} "
        f"wr_all={it['win_rate_all']:<6} dd={it['max_drawdown']:<6} "
        f"days={it['trading_days']:<5} fol={it['followers']}"
    )
# 找 6459
for it in items:
    if it["trader_id"] == "6459":
        print("\n6459 FOUND:", it)
        break
