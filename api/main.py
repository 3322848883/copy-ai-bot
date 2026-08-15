"""FastAPI 单体入口：路由注册、WS Hub 挂载、startup/shutdown（M0 + M1）。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.core.config import get_settings
from api.core.errors import AppError
from api.core.logging import setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.app_name)
    # M3 T3.0: 注册 5 家交易所适配器（dev mock / 生产官方签名）
    from api.exchange_clients.registry import init_adapters

    init_adapters()
    # M6 P0: 启动 pnl.tick 周期推送任务（首页实时盈亏）
    from api.ws.ticker import start_ticker

    ticker_task = await start_ticker()
    yield
    ticker_task.cancel()
    try:
        await ticker_task
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan, docs_url="/docs", openapi_url="/openapi.json")

# ── M6 T6.3 安全：CORS 白名单收紧（默认本地前端，生产经 CORS_ORIGINS 配置）──
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── M6 T6.3 安全：Redis 限流中间件（登录/支付/提现分级）──
from api.core.middleware import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


# ── M6 T6.5 监控：详细健康检查 + Prometheus /metrics（无前缀）──
from api.routers.monitoring import router as monitoring_router  # noqa: E402

app.include_router(monitoring_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}


# ── M1 路由注册 ──
from api.routers.v1 import auth as auth_router  # noqa: E402
from api.routers.v1 import identity as identity_router  # noqa: E402
from api.routers.v1 import apikeys as apikeys_router  # noqa: E402

app.include_router(auth_router.router, prefix=settings.api_prefix)
app.include_router(identity_router.router, prefix=settings.api_prefix)
app.include_router(apikeys_router.router, prefix=settings.api_prefix)

# ── M2 路由注册（信号采集 + 策略）──
from api.routers.v1 import strategies as strategies_router  # noqa: E402

app.include_router(strategies_router.router, prefix=settings.api_prefix)

# ── M3 路由注册（跟单机器人）──
from api.routers.v1 import bots as bots_router  # noqa: E402

app.include_router(bots_router.router, prefix=settings.api_prefix)

# ── M4 路由注册（订阅/支付/邀请/奖励/提现）──
from api.routers.v1 import subscriptions as subs_router  # noqa: E402
from api.routers.v1 import payments as payments_router  # noqa: E402
from api.routers.v1 import referrals as referrals_router  # noqa: E402
from api.routers.v1 import rewards as rewards_router  # noqa: E402
from api.routers.v1 import withdrawals as withdrawals_router  # noqa: E402

app.include_router(subs_router.router, prefix=settings.api_prefix)
app.include_router(payments_router.router, prefix=settings.api_prefix)
app.include_router(referrals_router.router, prefix=settings.api_prefix)
app.include_router(rewards_router.router, prefix=settings.api_prefix)
app.include_router(withdrawals_router.router, prefix=settings.api_prefix)

# ── M6 P0 路由注册（首页数据看板 + WebSocket 实时推送）──
from api.routers.v1 import dashboard as dashboard_router  # noqa: E402
from api.routers.v1 import ws as ws_router  # noqa: E402

app.include_router(dashboard_router.router, prefix=settings.api_prefix)
app.include_router(ws_router.router, prefix="/ws")

# ── M5 路由注册（后台 10 模块，prefix=/admin/v1，aud=admin）──
from api.routers.admin import auth as admin_auth  # noqa: E402
from api.routers.admin import users as admin_users  # noqa: E402
from api.routers.admin import exchange_invites as admin_exchange_invites  # noqa: E402
from api.routers.admin import signals as admin_signals  # noqa: E402
from api.routers.admin import withdrawals as admin_withdrawals  # noqa: E402
from api.routers.admin import payments as admin_payments  # noqa: E402
from api.routers.admin import audit as admin_audit  # noqa: E402
from api.routers.admin import risk as admin_risk  # noqa: E402
from api.routers.admin import signal_session as admin_signal_session  # noqa: E402
from api.routers.admin import orders as admin_orders  # noqa: E402
from api.routers.admin import review as admin_review  # noqa: E402
from api.routers.admin import wallets as admin_wallets  # noqa: E402
from api.routers.admin import invites as admin_invites  # noqa: E402

app.include_router(admin_auth.router, prefix=settings.admin_prefix)
app.include_router(admin_users.router, prefix=settings.admin_prefix)
app.include_router(admin_exchange_invites.router, prefix=settings.admin_prefix)
app.include_router(admin_signals.router, prefix=settings.admin_prefix)
app.include_router(admin_withdrawals.router, prefix=settings.admin_prefix)
app.include_router(admin_payments.router, prefix=settings.admin_prefix)
app.include_router(admin_audit.router, prefix=settings.admin_prefix)
app.include_router(admin_risk.router, prefix=settings.admin_prefix)
app.include_router(admin_signal_session.router, prefix=settings.admin_prefix)
app.include_router(admin_orders.router, prefix=settings.admin_prefix)
app.include_router(admin_review.router, prefix=settings.admin_prefix)
app.include_router(admin_wallets.router, prefix=settings.admin_prefix)
app.include_router(admin_invites.router, prefix=settings.admin_prefix)
