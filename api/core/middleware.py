# 安全中间件（M6 T6.3：Redis 限流 + 请求计数）
from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from api.core.config import get_settings

# 路径前缀 → (限流次数, 窗口秒)。登录 10/min 防爆破，支付 20/min，其余 120/min。
RATE_LIMITS: list[tuple[str, int, int]] = [
    ("/v1/auth/", 10, 60),
    ("/v1/payments", 20, 60),
    ("/v1/withdrawals", 10, 60),
    ("/v1/referrals/code", 30, 3600),
    ("/admin/v1/auth/", 10, 60),
    ("/v1/", 120, 60),
    ("/admin/v1/", 120, 60),
]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis 固定窗口限流：IP + 路径前缀。Redis 不可用时放行（dev 降级）。"""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.settings = get_settings()

    def _match(self, path: str) -> tuple[int, int] | None:
        for prefix, limit, window in RATE_LIMITS:
            if path.startswith(prefix):
                return limit, window
        return None

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(("/docs", "/openapi.json", "/healthz", "/metrics", "/redoc")):
            return await call_next(request)
        # ★ 2026-08 修复：CORS 预检 OPTIONS 不计限流（否则每次请求双倍消耗额度，
        #   且预检 429 会让浏览器直接 Failed to fetch）
        if request.method == "OPTIONS":
            return await call_next(request)

        rule = self._match(path)
        if rule is not None:
            limit, window = rule
            client_ip = request.client.host if request.client else "unknown"
            key = f"ratelimit:{client_ip}:{path.split('/')[2] if len(path.split('/')) > 2 else 'root'}:{int(time.time()) // window}"
            try:
                import redis

                r = redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
                count = r.incr(key)
                if count == 1:
                    r.expire(key, window + 5)
                if count > limit:
                    retry = window - (int(time.time()) % window)
                    return JSONResponse(
                        status_code=429,
                        content={"error": {"code": "rate_limited", "message": "请求过于频繁，请稍后再试", "detail": {"retry_after": retry}}},
                        headers={"Retry-After": str(retry)},
                    )
            except Exception:  # noqa: BLE001 Redis 不可用降级放行
                pass
        return await call_next(request)
