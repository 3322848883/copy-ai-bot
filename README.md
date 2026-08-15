# signal-saas 信号聚合跟单平台

跨 5 大交易所（Binance / OKX / Bybit / Bitget / Gate）信号聚合 + 一键跟单 SaaS。
平台不生产信号、不做自营、不抽水不返佣，唯一收入为订阅费。

## 功能全景

| 端 | 页面/模块 | 说明 |
|---|---|---|
| 前台 | 首页数据看板 | 4 指标卡（余额/奖励/机器人/订阅）、新手引导、我的跟单、实时行情、最近订单，WS 实时刷新 |
| 前台 | 登录 / 注册 | 邮箱注册 + 6 位验证码（5 分钟）、邀请码永久锁定、防自邀防循环 |
| 前台 | 策略广场 / 策略详情 | 带单员画像、收益曲线（SVG）、持仓与订单、一键创建跟单 |
| 前台 | 我的跟单 | 机器人列表、统计条、修改配置（比例/杠杆/模式）、删除（双重确认）、暂停/恢复 |
| 前台 | 邀请中心 / 奖励 | 邀请链接、海报生成、奖励明细（状态筛选 + 分页）、24h 倒计时 |
| 前台 | 提现 | 申请表单（TRC-20/BEP-20 地址正则校验）、记录列表、状态流转 |
| 前台 | 个人中心 | API Key 绑定/解绑、好友邀请码绑定、交易所选择 |
| 前台 | 订阅 | 试用（5U 仅 1 次）/ 正式（19.9U）套餐、多链 USDT 支付、自动核实 |
| 后台 | 12 模块 | 用户/信号源/跟单订单/主号下级审核/钱包账本/邀请奖励/支付订单/提现审核/风控/审计日志/交易所邀请码/信号会话 |
| 实时 | WebSocket 8 频道 | strategy.update / signal.new / bot.position / bot.order / pnl.tick / account.balance / reward.tick / withdrawal.status |

## 技术栈

- **后端**：Python 3.11 + FastAPI + SQLAlchemy（async）+ Alembic + Celery + Redis + JWT
- **前端**：Next.js 15（App Router）+ TypeScript，前台与后台同仓库隔离
- **执行层**：决策 B，弃用 ccxt，直接对接 5 家交易所官方 API（AES-256-GCM 凭证保险库）
- **数据**：PostgreSQL（生产）/ SQLite（本地开发一键直跑）
- **监控**：Prometheus + Grafana + `/metrics` + `/healthz`

## 架构决策

- **决策 B**：执行层直接对接 5 家官方 API（`api/exchange_clients/`），适配器统一接口（test_connect / fetch_balance / check_permissions / place_order）。
- **单体**：后端为单个 FastAPI 应用（`api/`），19 业务服务模块 + 前台/后台双端。
- **隔离**：后台与前台完全隔离（独立登录 / JWT aud=admin / 写操作强制 audit-log）。
- **双轨信号源**：模式 A 爬虫（Gate 带单广场，3-8s）/ 模式 B 跟单账户 WS 镜像（1.5-3s），信号清洗标准化，延迟红线 A>10s、B>5s 丢弃。
- **跟单引擎**：USDT 本位换算 4 步法、独立虚拟账本隔离、8 类失败归因、币种/精度/余额风控。
- **订阅变现**：试用/正式双套餐、多链支付自动核实（即时 3 项 + 4 次轮询）、到期禁开仓加仓、试用限购数据库强校验。
- **邀请奖励**：10% 奖励 + 24h 延迟核实（防退款回滚）、1h 批量 5U 防刷检测、负数冻结提现。
- **需求修复**：G03-G27 编号跟踪（见 `docs/2026-08-12-signal-saas-platform-design.md`）。

## 目录结构

```
信号聚合AI/
├── api/                 # FastAPI 单体后端
│   ├── core/            # config / security(JWT+Vault) / logging / metrics / middleware
│   ├── db/              # base / session / migrations(Alembic)
│   ├── models/          # 18 张 ORM 表（audit/billing/bot/exchange/signal/user）
│   ├── schemas/         # Pydantic 请求/响应
│   ├── routers/         # v1（前台 13 路由）+ admin（后台 13 路由，隔离）
│   ├── services/        # 19 个业务服务模块
│   ├── exchange_clients/# 5 家官方客户端适配器（决策 B）
│   ├── workers/         # Celery 任务（信号/画像/奖励/支付/提醒）
│   ├── ws/              # WebSocket Hub（8 频道 + pnl.tick 周期推送）
│   └── tests/           # 单元 + 集成测试
├── web-ui/              # Next.js 15 前端（前台 + admin/ 后台）
│   ├── app/             # 页面路由（含 admin/ 12 后台页面）
│   ├── components/      # Nav / WsProvider / AdminShell / RiskDisclosureModal 等
│   └── lib/             # api 客户端 + ws 客户端（心跳/重连/频道分发）
├── deploy/              # docker-compose + prometheus + grafana
├── docs/                # 设计 / 框架 / 开发计划 / 验收报告 / UI 成品（33 份）
├── scripts/             # 建库 / 种子 / 验证脚本
└── data/                # 运行时数据（signal_session 会话，不入库）
```

## 快速开始（本地 SQLite 直跑）

```bash
# 1. 创建并激活 venv
python -m venv .venv
# Windows: .venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 用 SQLite 本地库启动后端（无需 Docker）
set DATABASE_URL=sqlite+aiosqlite:///./dev.db
uvicorn api.main:app --reload
# 健康检查: http://localhost:8000/healthz
# API 文档: http://localhost:8000/docs

# 4. 初始化演示数据（策略/画像/机器人/订单/订阅/邀请/奖励）
python scripts/rebuild_devdb.py
python scripts/seed_demo.py

# 5. 启动前端
cd web-ui
npm install
npm run dev
# 前台: http://localhost:3000   后台: http://localhost:3000/admin/login
```

> 本地测试账号：`alice@test.com / test123456`（前台用户），`admin@test.com / admin123456`（后台管理员）。

## 环境变量（`.env`）

| 变量 | 说明 | 本地默认 |
|---|---|---|
| `APP_ENV` / `DEBUG` | 运行环境 / 调试开关 | `dev` / `true` |
| `JWT_SECRET` | JWT 签名密钥（生产必换） | `dev-secret-...` |
| `VAULT_KEY_HEX` | API Key 加密主密钥（AES-256-GCM） | 64 位 hex |
| `DATABASE_URL` | 数据库连接串 | PG `postgresql+asyncpg://signal:signal@localhost:5432/signal_saas` |
| `REDIS_URL` | Redis（限流/Celery） | `redis://localhost:6380/0` |
| `SMTP_HOST/PORT/MAIL_FROM` | 邮件（验证码，Mailhog 本地调试） | `localhost:1025` |
| `SCRAPER_REAL` / `SCRAPER_HEADLESS` | 模式 A 真实采集开关 / 有头模式 | `1` / `false` |
| `SIGNAL_FOLLOWER_LEADER_IDS` | 模式 B 跟单 leader_id 列表 | `["32801","24264"]` |
| `SIGNAL_SESSION_ENABLED` | 持久化浏览器会话（后台登录 Gate） | `true` |

## API 概览

- 前台 `api/routers/v1/`：auth、identity、account、apikeys、strategies、bots、dashboard、subscriptions、payments、referrals、rewards、withdrawals、ws
- 后台 `api/routers/admin/`（prefix `/admin/v1`，aud=admin）：auth、users、exchange_invites、signals、withdrawals、payments、audit、risk、signal_session、orders、review、wallets、invites
- 实时 `GET /ws/stream?token=<JWT>`：鉴权（aud=web）后推送 8 频道，30s 心跳保活，断线自动重连

## 里程碑

| M | 内容 | 状态 |
|---|------|------|
| M0 | 仓库初始化 + api 单体骨架 | ✅ 已完成 |
| M1 | 注册/身份/API Key 保险库/审计 | ✅ 已完成 |
| M2 | 双轨信号采集 + 策略包装 | ✅ 已完成 |
| M3 | 跟单引擎 + 风控 + 模拟盘 | ✅ 已完成 |
| M4 | 订阅 + 支付 + 邀请奖励 + 提现 | ✅ 已完成 |
| M5 | 后台 12 模块 + 前台闭环 | ✅ 已完成 |
| M6 | 首页数据看板 + WebSocket 实时推送 + 监控合规 | ✅ 已完成 |

详见 `docs/2026-08-12-signal-saas-v1-development-plan.md` 与 `docs/2026-08-12-signal-saas-requirements-coverage-check.md`。

## 测试与验证

```bash
# 后端（依赖 dev 工具链：pip install -e "api[dev]"）
cd api && python -m pytest tests/ -v

# 前端类型检查
cd web-ui && npx tsc --noEmit
```

CI（GitHub Actions `.github/workflows/ci.yml`）：push/PR 到 main 自动跑 ruff（E9/F 硬错误）+ pytest + tsc + build。

端到端验收记录见 `docs/2026-08-12-signal-saas-design-gap-analysis.md`（演示 HTML 与真实实现差异核对）、`docs/2026-08-13-celery-full-link-verification.md`（Celery 全链路）。

## 文档索引（docs/）

- 平台设计：`2026-08-12-signal-saas-platform-design.md`（含 G03-G27 需求编号）
- 开发计划：`2026-08-12-signal-saas-v1-development-plan.md`
- 需求覆盖核对：`2026-08-12-signal-saas-requirements-coverage-check.md`
- 差异分析与验收：`2026-08-12-signal-saas-design-gap-analysis.md`
- 框架与 UI 成品：`2026-08-12-signal-saas-*-framework.md` / `*.html`（前台/后台全部页面高保真蓝本）
- Gate POC 验证：`2026-08-12-gate-poc-verification-report.md`
