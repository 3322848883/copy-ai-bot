"""核心配置（pydantic-settings，环境变量驱动）。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ★ 项目根目录 = config.py 的上一级(api/core -> api -> 根)。用绝对路径加载 .env，
#   避免进程启动目录不在项目根时读不到配置（表现为功能开关全部落回默认值）。
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """全局配置，集中读取环境变量（.env 支持）。"""

    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    # ── 应用 ──
    app_name: str = "OmniAlpha"
    # ★ P1 安全默认：缺省按 prod 跑（fail-fast 生效）。忘配 APP_ENV 时宁可启动失败，
    #   不可静默落入 dev——dev 下 mock 链客户端/固定验证码/Gate 假成交等测试后门全部生效
    app_env: str = "prod"  # dev / test / prod
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

    # ── 交易所（决策 B 官方直连；V1 生产白名单默认仅 gate）──
    enabled_exchanges: str = "gate"

    def enabled_exchange_list(self) -> list[str]:
        """逗号分隔解析为列表（与 CORS 同模式）。"""
        return [x.strip() for x in self.enabled_exchanges.split(",") if x.strip()]

    # ── 风控（默认值，后台可配置）──
    delay_redline_mode_a_ms: int = 10_000  # 模式 A 爬虫
    delay_redline_mode_b_ms: int = 5_000   # 模式 B WS
    withdraw_min_usdt: float = 10.0        # ★ G13
    withdraw_fee_usdt: float = 1.0

    # ── 支付三链确认阈值（★ G09：唯一权威源为 chain_client.REQUIRED_CONFIRMATIONS，此处已废弃）──

    # ── 链上 RPC（生产必填/可换自建或付费节点）──
    tron_rpc_url: str = "https://api.trongrid.io"
    bsc_rpc_url: str = "https://bsc-dataseed.binance.org"
    eth_rpc_url: str = "https://eth.llamarpc.com"
    aptos_rpc_url: str = "https://fullnode.mainnet.aptoslabs.com/v1"
    # APTOS 上的 USDT 资产类型（LayerZero/Bridge 桥接标准合约，6 位小数）
    aptos_usdt: str = "0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDT"

    # ── 邮件（SMTP）──
    smtp_host: str = "localhost"
    smtp_port: int = 1025  # Mailhog
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "no-reply@signal-saas.com"

    # ── M6 T6.3 安全：CORS 白名单（逗号分隔），生产收紧 ──
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # ★ 本地生产测试专用：显式开启后允许 localhost/127.0.0.1 进 CORS 白名单
    #   仅用于本机无域名/无 nginx 反代的跨源联调；生产部署绝不设置此开关
    cors_allow_local_test: bool = False

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
    # ★ 页面池自适应上限：按实际监控交易员数动态扩缩（_resize_pool），
    #   扩容立即、缩容保守（留缓冲防跟单波动抖动），上限封顶防内存爆。
    #   16 页 ≈ 2.4GB（~150MB/页），5.8GB 服务器安全；50+ 交易员时约 5s/轮。
    scraper_max_pages: int = 16
    # ★ 缩容缓冲：当前池 > 需要 + 缓冲 才回收尾部页面（防频繁建/关抖动）
    scraper_pool_shrink_buf: int = 4
    # ★ 方案B：公开爬虫独立 user_data_dir（与登录会话 signal_session_data_dir 彻底隔离）。
    #   公开接口(模式A)走此目录的浏览器；私有接口(模式B)走登录会话，互不争抢 Chrome profile 锁。
    scraper_data_dir: str = "data/scraper"
    # ★ 批量任务（scrape_all/refresh_listed_profiles/reconcile）独立 user_data_dir：
    #   poll_live 热循环几乎 100% 占用 data/scraper（Chromium ProcessSingleton 同一
    #   profile 同时只允许一个实例），批量任务抢同目录必然锁冲突——实测 refresh
    #   ensure_browser_ready 90s 全超时。独立 profile 后二者并行互不干扰，
    #   批量任务也无需再持差分锁排他（poll 不再被致盲）。
    scraper_bulk_data_dir: str = "data/scraper-bulk"
    # ★ 浏览器代理（gate.com 等被墙站点必须走代理；Chromium 不读环境变量，须显式传 launch(proxy=)）
    #   空=不走代理。容器内格式 http://host.docker.internal:<port>（本机 Clash 需中继/局域网监听）
    browser_proxy_url: str = ""

    # ── 实时信号轮询（★实测 2026-08：1 秒轮询公开接口 2000+ 请求 0 次 403）──
    signal_poll_interval: int = 1      # 轮询间隔(秒)；带单员分钟级交易，1 秒不丢单
    signal_poll_loop_seconds: int = 110 # 单次任务连续运行时长(秒)；beat 调度间隔
    #   = 本值 + 10s 余量（celery_app.py）：任务总耗时 = 循环 + 浏览器启停开销(~1-10s)，
    #   若调度间隔 == 循环时长，相邻两轮任务永久重叠互抢 user_data_dir
    #   （ProcessSingleton 锁），各损 ~30 轮询
    #   ★ 50→110（2026-08-20）：拉长单任务时长降低空窗占比（浏览器重启间隙不可轮询）：
    #     50s循环+65s调度 = 23% 时间盲区；110s+120s = 8%。更少冷启动也降低 Akamai 挑战概率
    signal_change_threshold: float = 0.005  # 持仓占比阈值：低于则视为噪音过滤(0.5%)
    signal_reconcile_interval: int = 600    # 全量对账间隔(秒)：强制重同步基线防漂移
    # ★ 公开广场采集覆盖数：signal.scrape_all 每轮抓取榜单前 N 名带单员
    signal_scrape_limit: int = 8
    # ★ 已跟单交易员自动同步间隔(秒)：同步需拉起登录会话浏览器，与 admin 远程
    #   操作争抢 user_data_dir；跟单关系低频变化，默认 10 分钟足够。
    signal_follow_sync_interval: int = 600
    # ★ 测试符号过滤：真实数据中曾混入 TESTUSDT，symbol 含任一标记即丢弃
    signal_test_symbols: tuple[str, ...] = ("TEST", "DEMO", "FAKE")
    # ★ 模式2 信号源：通过这些「跟单账户 leader_id」监控（JSON 数组格式，如 ["32801","24264"]）。
    #   模式2 只监控「自己已跟单」的镜像仓位，按 leader_id 精确对应；未跟单的带单员无法监控。
    #   ★ 留空时由 fetch_followed_leaders 自动发现（推荐：mock 时期的默认值已清除）。
    signal_follower_leader_ids: tuple[str, ...] = ()
    # ★ 需求补充：信号源详情(画像)定时刷新间隔(秒)。无论模式一/模式二，已上架(listed)
    #   策略的带单员画像都要定期刷新，保证策略广场数据新鲜（不只依赖每日快照）。
    signal_profile_refresh_interval: int = 1800
    # ★ 源信号保留期（天）：超期的 source_signals 记录由每日清理任务删除，
    #   防止信号表无限增长导致查询性能退化。默认 90 天，约覆盖 1 个季度的信号追溯。
    signal_retention_days: int = 90
    # ★ 持仓快照保留期（天）：超期且已关闭(is_open=False)的 position_snapshots
    #   由每日清理任务删除。当前 open 的仓位不受影响。默认 30 天。
    position_snapshot_retention_days: int = 30

    # ── 模式2 信号源·持久化浏览器会话（后台管理「登录 Gate」）──
    #   服务器端维护一个持久化 Chrome(user_data_dir)，登录态自动落盘，
    #   后台管理通过「截图推送+事件转发」远程完成登录，供 fetch_follower_positions 复用。
    signal_session_enabled: bool = False
    signal_session_data_dir: str = "data/signal_session"   # 持久化浏览器 user_data_dir 根目录
    signal_session_headless: bool | None = None            # None=生产默认; 参考 scraper_headless
    signal_session_screenshot_interval: float = 0.5        # 登录串流截图轮询间隔(秒)

    # ── 应用公开地址（邮件/站内链接）──
    app_public_base_url: str = "http://localhost:3000"

    @model_validator(mode="after")
    def _validate_prod(self) -> "Settings":
        """★ M6 T0.6：生产环境密钥 fail-fast——缺配置/用默认值直接拒绝启动。"""
        # ★ P1 修复：拼写错误（staging/production 等）不允许静默按非 prod 宽松模式运行
        if self.app_env not in ("dev", "test", "prod"):
            raise ValueError(f"APP_ENV 非法: {self.app_env}（仅允许 dev/test/prod）")
        if self.app_env != "prod":
            return self
        errors: list[str] = []
        if self.jwt_secret == "change-me-in-prod" or len(self.jwt_secret) < 32:
            errors.append("JWT_SECRET 必须 ≥32 位且非默认值")
        if self.debug is not False:
            errors.append("DEBUG 生产必须为 false")
        if self.vault_key_hex == "0" * 64 or len(self.vault_key_hex) != 64:
            errors.append("VAULT_KEY_HEX 必须为 64 位 hex 且非全 0")
        else:
            try:
                bytes.fromhex(self.vault_key_hex)
            except ValueError:
                errors.append("VAULT_KEY_HEX 必须为合法 hex 字符集")
        if self.smtp_host in ("localhost", "mailhog"):
            errors.append("SMTP_HOST 不能为本地调试地址（mailhog）")
        if "*" in self.cors_origins or not self.cors_origins.strip():
            errors.append("CORS_ORIGINS 生产不能为 * 或空")
        # ★ 修复：生产 CORS 拒绝 localhost/127.0.0.1（纵深防御，防止默认白名单上线）
        #   本地生产测试可显式设 CORS_ALLOW_LOCAL_TEST=1 放行（仅本机联调）
        if any(h in self.cors_origins for h in ("localhost", "127.0.0.1")) and not self.cors_allow_local_test:
            errors.append("CORS_ORIGINS 生产不能包含 localhost/127.0.0.1")
        # ★ 修复：拦截任意 host 的默认弱口令连接串（含 signal:signal@db 等）
        if "://signal:signal@" in self.database_url:
            errors.append("DATABASE_URL 不能使用默认弱口令 signal:signal")
        if not self.enabled_exchange_list():
            errors.append("ENABLED_EXCHANGES 不能为空")
        if errors:
            raise ValueError("生产配置缺失: " + "; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
