"""临时：四链（trc20/bep20/erc20/aptos）真实下单联调（dev mock 确认）。"""
import asyncio
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
NETWORKS = ["trc20", "bep20", "erc20", "aptos"]
PLAN = "monthly_19_9u"  # 正式套餐，无限购，可在同一 user 上跑满四链


def show(label: str, r: httpx.Response, j=None) -> None:
    code = r.status_code
    j = j if j is not None else (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
    print(f"[{label}] HTTP {code} -> {j if isinstance(j, str) else _clip(j)}")


def _clip(j, n=260) -> str:
    s = str(j)
    return s if len(s) <= n else s[:n] + "…"


async def main() -> None:
    email = f"chain4_{int(time.time())}@test.com"
    pwd = "testChain#2026"
    async with httpx.AsyncClient(base_url=BASE, timeout=30, trust_env=False) as c:
        # 1) 注册
        r = await c.post("/v1/auth/register", json={"email": email, "password": pwd})
        show("register", r)
        # 2) 验证邮箱（dev 固定验证码）
        r = await c.post("/v1/auth/verify-email", json={"email": email, "code": "123456"})
        show("verify-email", r)
        # 3) 登录
        r = await c.post("/v1/auth/login", json={"email": email, "password": pwd})
        show("login", r)
        tok = (r.json() or {}).get("access_token")
        if not tok:
            print("!! 无 access_token，中止；可先关闭验证码或直接 seed 用户")
            return
        headers = {"Authorization": f"Bearer {tok}"}
        # 4) 风险声明（支付前如需）
        try:
            await c.post("/v1/auth/accept-risk-disclosure", headers=headers)
        except Exception:
            pass

        # 5) 套餐
        r = await c.get("/v1/subscriptions/plans", headers=headers)
        plans = (r.json() or {}).get("plans", [])
        print("[plans] " + _clip(plans, 300))

        for net in NETWORKS:
            ts = int(time.time())
            r = await c.post("/v1/payments", headers=headers, json={"plan_id": PLAN, "network": net})
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            show(f"create-order {net}", r, j)
            order_id = (j or {}).get("order_id")
            if not order_id:
                print(f"  !! {net} 下单失败，跳过提交")
                continue
            print(f"    ⇒ platform_address={j.get('platform_address')} required={j.get('required_confirmations')} amount={j.get('amount_usdt')}")
            tx = f"mock_confirm_chain4_{net}_{ts}"
            r = await c.post(f"/v1/payments/{order_id}/tx", headers=headers, json={"tx_hash": tx})
            show(f"submit-tx {net}", r)
            r = await c.get(f"/v1/payments/{order_id}", headers=headers)
            show(f"get-order {net}", r)

        # 6) 订阅确认
        r = await c.get("/v1/subscriptions/me", headers=headers)
        show("subscriptions/me", r)
        # 7) 订单历史
        r = await c.get("/v1/payments/orders", headers=headers)
        show("orders", r)


if __name__ == "__main__":
    asyncio.run(main(), debug=False)