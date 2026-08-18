# -*- coding: utf-8 -*-
"""排查：待选池当前状态。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE = "http://localhost:8000"

EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "")
PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "")
if not EMAIL or not PASSWORD:
    print("ERROR: 请设置 SEED_ADMIN_EMAIL 与 SEED_ADMIN_PASSWORD 环境变量", file=sys.stderr)
    sys.exit(1)


def main():
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{BASE}/admin/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        access = r.json().get("access_token")
        h = {"Authorization": f"Bearer {access}"}

        r = c.get(f"{BASE}/admin/v1/signals/pending", headers=h)
        print("PENDING STATUS:", r.status_code)
        data = r.json()
        items = data.get("items", [])
        print(f"PENDING ITEMS: {len(items)}")
        for it in items[:5]:
            print(f"  {it}")

        r = c.get(f"{BASE}/admin/v1/signals", headers=h)
        data = r.json()
        items = data.get("items", [])
        print(f"\nLISTED ITEMS: {len(items)}")
        for it in items:
            print(f"  id={it['id']} name={it['display_name']!r} status={it['status']}")


if __name__ == "__main__":
    main()
