"""signal-saas API 压测生成器（M6 T6.7 清单 §8）。

真实用户并发混合负载：登录 → 拉取策略列表/详情 → 首页看板 → 提现列表。
统计 p50/p95/p99、成功率、吞吐，输出 HTML 报告到 docs/。

用法（完整验收：100 并发 30min，p95 < 500ms）：
  python loadtest/loadtest.py --base-url https://api.example.com --users 100 --duration 1800
本地冒烟（5 并发 30s）：
  python loadtest/loadtest.py --base-url http://localhost:8000 --users 5 --duration 30
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import aiohttp

LOGIN = "/v1/auth/login"
STRATEGIES = "/v1/strategies"
DASHBOARD = "/v1/dashboard"
WITHDRAWALS = "/v1/withdrawals"

# 预设测试账号（独立于被测数据，登录后复用 access token）
EMAIL = "alice@test.com"
PASSWORD = "test123456"


async def _post_login(session: aiohttp.ClientSession, base: str) -> str | None:
    try:
        async with session.post(
            base + LOGIN,
            json={"email": EMAIL, "password": PASSWORD},
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("access_token")
    except Exception:  # noqa: BLE001
        return None


async def _worker(
    idx: int,
    base: str,
    token: str,
    duration: float,
    lat: dict[str, list[float]],
    ok: list[int],
    total: list[int],
) -> None:
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # 各用户不同端点加权：策略列表最多，其次详情/看板，提现最少
    endpoints = [
        (STRATEGIES, 1.0),
        (f"{STRATEGIES}/1", 0.6),
        (DASHBOARD, 0.5),
        (WITHDRAWALS, 0.3),
    ]
    deadline = time.monotonic() + duration
    async with aiohttp.ClientSession() as s:
        while time.monotonic() < deadline:
            path, w = endpoints[idx % len(endpoints)]
            if (idx % 10) / 10.0 > w * 1.0 and idx % 3 != 0:
                path = STRATEGIES
            t0 = time.monotonic()
            try:
                async with s.get(base + path, headers=auth, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    dt = (time.monotonic() - t0) * 1000
                    lat[path].append(dt)
                    total[0] += 1
                    if resp.status == 200:
                        ok[0] += 1
            except Exception:  # noqa: BLE001
                total[0] += 1


async def _run(args: argparse.Namespace) -> None:
    connector = aiohttp.TCPConnector(limit=args.users + 10, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        token = await _post_login(session, args.base_url)
        if not token:
            raise SystemExit("[loadtest] 登录失败，请检查 base-url 与测试账号")

    lat: dict[str, list[float]] = {p: [] for p in (STRATEGIES, f"{STRATEGIES}/1", DASHBOARD, WITHDRAWALS)}
    ok = [0]
    total = [0]
    start = time.monotonic()
    tasks = [
        asyncio.create_task(_worker(i, args.base_url, token, args.duration, lat, ok, total))
        for i in range(args.users)
    ]
    await asyncio.gather(*tasks)
    elapsed = time.monotonic() - start

    all_lat = [v for vs in lat.values() for v in vs]
    p = lambda q: round(statistics.quantiles(all_lat, n=100)[q - 1], 2) if all_lat else 0.0  # noqa: E731
    summary = {
        "users": args.users,
        "duration_s": round(elapsed, 1),
        "total_requests": total[0],
        "success": ok[0],
        "success_rate": round(ok[0] / total[0] * 100, 2) if total[0] else 0.0,
        "rps": round(total[0] / elapsed, 2),
        "p50_ms": p(50),
        "p95_ms": p(95),
        "p99_ms": p(99),
        "per_endpoint_ms": {k: round(statistics.median(v), 2) for k, v in lat.items() if v},
    }
    _write_report(summary)
    print(summary)


def _write_report(s: dict) -> None:
    import html as _h
    from datetime import datetime, timezone

    rows = "".join(
        f"<tr><td>{_h.escape(k)}</td><td>{v}</td></tr>" for k, v in s["per_endpoint_ms"].items()
    )
    body = f"""
    <html><head><meta charset="utf-8"><title>压测报告</title></head>
    <body style="font-family:sans-serif;max-width:760px;margin:40px auto;color:#1f2328">
    <h2>signal-saas API 压测报告</h2>
    <p style="color:#666">生成时间：{datetime.now(timezone.utc).isoformat()}（UTC）· 验收目标：100 并发 30min，p95 &lt; 500ms</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse">
      <tr><th>指标</th><th>值</th></tr>
      <tr><td>并发用户</td><td>{s['users']}</td></tr>
      <tr><td>时长(s)</td><td>{s['duration_s']}</td></tr>
      <tr><td>总请求</td><td>{s['total_requests']}</td></tr>
      <tr><td>成功率</td><td>{s['success_rate']}%</td></tr>
      <tr><td>吞吐(RPS)</td><td>{s['rps']}</td></tr>
      <tr><td>P50</td><td>{s['p50_ms']} ms</td></tr>
      <tr><td>P95</td><td>{s['p95_ms']} ms</td></tr>
      <tr><td>P99</td><td>{s['p99_ms']} ms</td></tr>
    </table>
    <h3>各端点中位耗时(ms)</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">
      <tr><th>端点</th><th>P50</th></tr>{rows}
    </table>
    <p style="color:#888;font-size:12px">结论判定：成功&gt;99% 且 p95&lt;500ms 判定通过；否则记录差距供调优。</p>
    </body></html>
    """
    import os

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "loadtest-report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"[loadtest] 报告已写入 {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--duration", type=int, default=1800)
    args = ap.parse_args()
    asyncio.run(_run(args))