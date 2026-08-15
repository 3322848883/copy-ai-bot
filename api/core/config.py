"""核心配置（pydantic-settings，环境变量驱动）。"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，集中读取环境变量（.env 支持）。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── 应用 ──
    app_name: str = "signal-saas"
    app_env: str = "dev"  # dev / test / prod
    debug: bool = True
    api_prefix: str = "/v1"
    admin_prefix: str = "/admin/v1"
    ws_path: str = "/ws/stream"

    # ── 安全 ──
    jwt_secret: str = "change-me-in-prod"
    jwt_audience: str = "web"  # 前台 aud；后台为 admin（完全隔离）
    jwt_admin_audience: str = "admin"
    jwt_expire_minutes: int = 60 * 24  # 1 天
    jwt_refresh_expire_days: int = 7
    password_min_length: int = 8
    # AES-256-GCM 凭证保险库
    vault_key_hex: str = "0" * 64  # 64 hex = 32 bytes；生产必须替换

    # ── 数据库 ──
    database_url: str = "postgresql+asyncpg://signal:signal@localhost:5432/signal_saas"
    redis_url: str = "redis://localhost:6379/0"

    # ── 交易所（决策 B 官方直连）──
    enabled_exchanges: tuple[str, ...] = ("gate", "binance", "okx", "bybit", "bitget")

    # ── 风控（默认值，后台可配置）──
    delay_redline_mode_a_ms: int = 10_000  # 模式 A 爬虫
    delay_redline_mode_b_ms: int = 5_000   # 模式 B WS
    withdraw_min_usdt: float = 10.0        # ★ G13
    withdraw_fee_usdt: float = 1.0

    # ── 支付三链确认阈值（★ G09）──
    confirmations_required: dict[str, int] = {"trc20": 12, "bep20": 15, "erc20": 12}

    # ── 邮件（SMTP）──
    smtp_host: str = "localhost"
    smtp_port: int = 1025  # Mailhog
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "no-reply@signal-saas.com"

    # ── M6 T6.3 安全：CORS 白名单（逗号分隔），生产收紧 ──
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ── M6 T6.1 灰度默认值 ──
    strategy_default_gray_pct: int = 20

    # ── 真实信号源采集（M2 生产：Playwright 抓 Gate 带单广场；dev 默认 mock）──
    scraper_real: bool = False
    # ★ 无头可配置（服务器部署更友好）：None=自动(prod 默认无头)，True/False 强制
    #   生产默认无头(new 模式)，指纹难区分且无需显示；若 Akamai 拦截可设 false 走有头(xvfb)
    scraper_headless: bool | None = None
    # ★ 无头模式：new=现代无头(推荐，指纹难区分) / old=旧无头(易被检测)
    scraper_headless_mode: str = "new"
    # ★ 页面池并发：同一浏览器(context)内并行的页面数，用于并发拉取多个带单员持仓。
    #   1 个浏览器 = 1 套指纹/cookie 身份，页面数决定并发上限（每页独立 fetch 互不阻塞）。
    #   默认 4：单个交易所几十个带单员时，单轮耗时 ≈ 交易员数/池大小 × 单次往返。
    scraper_page_pool_size: int = 4

    # ── 实时信号轮询（★实测 2026-08：1 秒轮询公开接口 2000+ 请求 0 次 403）──
    signal_poll_interval: int = 1      # 轮询间隔(秒)；带单员分钟级交易，1 秒不丢单
    signal_poll_loop_seconds: int = 60 # 单次任务连续运行时长(秒)，到点交还 celery 重踢
    signal_change_threshold: float = 0.005  # 持仓占比阈值：低于则视为噪音过滤(0.5%)
    signal_reconcile_interval: int = 600    # 全量对账间隔(秒)：强制重同步基线防漂移
    # ★ 测试符号过滤：真实数据中曾混入 TESTUSDT，symbol 含任一标记即丢弃
    signal_test_symbols: tuple[str, ...] = ("TEST", "DEMO", "FAKE")
    # ★ 模式2 信号源：通过这些「跟单账户 leader_id」监控（带单员 leader_id 列表，逗号分隔）。
    #   模式2 只监控「自己已跟单」的镜像仓位，按 leader_id 精确对应；未跟单的带单员无法监控。
    signal_follower_leader_ids: tuple[str, ...] = ()

    # ── 模式2 信号源·持久化浏览器会话（后台管理「登录 Gate」）──
    #   服务器端维护一个持久化 Chrome(user_data_dir)，登录态自动落盘，
    #   后台管理通过「截图推送+事件转发」远程完成登录，供 fetch_follower_positions 复用。
    signal_session_enabled: bool = False
    signal_session_data_dir: str = "data/signal_session"   # 持久化浏览器 user_data_dir 根目录
    signal_session_headless: bool | None = None            # None=生产默认; 参考 scraper_headless
    signal_session_screenshot_interval: float = 0.5        # 登录串流截图轮询间隔(秒)


@lru_cache
def get_settings() -> Settings:
    return Settings()
