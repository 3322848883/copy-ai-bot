# signal-saas 项目框架设计文档

> 路径：`c:\Users\w6485\Desktop\AI 量化\.trae\documents\2026-08-12-signal-saas-project-framework.md`
> 定位：把需求文档（1-10 章）、设计蓝本（`2026-08-12-signal-saas-platform-design.md`）、开发计划（`2026-08-12-signal-saas-v1-development-plan.md`）落实为可执行的**工程骨架**。
> 目标：一个完整的 Web 应用，单体后端 + 双前端，目录结构、模块边界、依赖注入、数据层、异步任务、部署方式全部落地。
> 版本：v1（2026-08-12）

---

## 1. 技术栈总览

| 层 | 选型 | 用途 | 依据 |
|---|---|---|---|
| 后端 | **FastAPI**（Python 3.11） | 唯一 HTTP/WSS 入口，单体应用 | 设计 §3.3 |
| 前端用户 | **Next.js 14**（App Router + TypeScript） | web-ui 用户 SPA | 设计 §3.1 |
| 前端管理 | **Next.js 14** | web-admin 后台，与前台完全隔离 | 设计 §3.2 |
| ORM | **SQLAlchemy 2.0** + **Alembic** | 数据模型与迁移 | 设计 §4 |
| 数据库 | **PostgreSQL 15** | 唯一业务库（表和状态机） | 简化后收敛 |
| 缓存/队列 | **Redis 7** + **Celery** | 异步任务（爬虫/画像/支付轮询）、Pub/Sub | 保留 |
| 凭证加密 | **cryptography**（AES-256-GCM） | 交易所 API key 加密 | 设计 §3.11 |
| 交易所 | **官方 API 直连**（REST + WS），自研客户端 | 5 家执行，签名/限流/重连自研 | 决策 B |
| 区块链 | **tronpy** + **web3.py** | TRC-20/BEP-20/ERC-20 校验 | 设计 §3.7 |
| 爬虫 | **Playwright** | 带单广场公开数据 | 设计 §3.12 |
| 邮件 | **aiosmtplib** | SMTP 验证码/通知 | 设计 §3.20 |
| 测试 | **pytest** + **httpx** | 单测/接口测试 | 开发计划 DoD |
| 部署 | **Docker Compose** | 一键起全部服务 | 开发计划 M0 |

**单体决策**：整个后端是一个 FastAPI 进程，21 个模块是 `api/` 内的 Python 包，模块间通过**函数调用 + 依赖注入**协作，跨模块事件用 Redis Pub/Sub 与 Celery 队列。不引入微服务、gRPC、独立服务进程。

**交易所对接决策（决策 B，2026-08-12）**：执行层**直接对接 5 家交易所官方 API（Binance/OKX/Bybit/Bitget/Gate），弃用 ccxt**。原因：ccxt 在 OKX/Bitget/Binance 等适配器硬编码了默认 `brokerId`/referral 代码抽取返佣；本项目返佣归属需清晰。官方 REST + WS 文档完整，5 家签名/限流/重连自研可控。执行层保留统一 `ExchangeAdapter` 抽象，未来可扩展新所。
> ✅ **POC 已验证（2026-08-12）**：Gate 单家 POC 通过——签名(HMAC-SHA512)、公开合约规格(907 合约,ContractSpec 字段),私有 WS 认证+订阅全部跑通。详见 [Gate POC 验证报告](./2026-08-12-gate-poc-verification-report.md)。真实下单受账户资金阻塞，待补充资金后验证。

---

## 2. 顶层目录结构

```
signal-saas/
├── api/                        # FastAPI 单体后端（唯一后端）
├── web-ui/                     # Next.js 14 用户前台
├── web-admin/                  # Next.js 14 后台
├── deploy/                     # 部署编排
│   ├── docker-compose.yml
│   ├── prometheus/
│   ├── grafana/
│   └── nginx/
├── tests/                      # 跨模块集成测试与 fixtures
├── pyproject.toml              # 后端依赖与工具配置
├── .env.example                # 所有环境变量模板
├── .github/workflows/ci.yml    # CI
└── README.md
```

> 相比开发计划 §1.3 的旧骨架：**移除独立的 `auth-svc/ ... 21 modules` 平铺目录**，全部收敛进 `api/`；移除 `deploy/` 下不需要的微服务编排，保留 Compose、Prometheus、Grafana。

---

## 3. 后端 api 目录结构（单体）

```
api/
├── main.py                     # FastAPI 实例、路由注册、WS Hub 挂载、startup/shutdown
├── deps.py                     # 全局依赖：db session、auth、audit、services 容器
├── core/                       # 跨模块基础设施
│   ├── config.py               # pydantic-settings 配置（环境变量）
│   ├── security.py             # JWT 签发/校验、bcrypt 密码、AES-256-GCM 凭证保险库
│   ├── logging.py              # 结构化日志 + trace_id
│   ├── metrics.py              # Prometheus 指标工厂
│   └── errors.py               # 统一异常与错误码
├── db/
│   ├── base.py                 # SQLAlchemy Base + 通用模型 mixin
│   ├── session.py              # async engine / sessionmaker
│   └── migrations/             # Alembic 迁移目录
├── models/                     # SQLAlchemy ORM 模型（对应设计 §4.2）
│   ├── user.py                 # User / Identity / IdentityExchange / ApiKey
│   ├── exchange.py             # Exchange / ContractSpec / PlatformPool
│   ├── signal.py               # SourceSignal / Trader / Strategy / TraderProfile
│   ├── bot.py                  # CopyBot / CopyOrder / PositionSnapshot
│   ├── billing.py              # Subscription / PaymentOrder / Reward / Withdrawal / Invite
│   └── audit.py                # AuditEvent / Notification
├── schemas/                    # Pydantic 请求/响应模型（API 边界）
│   ├── auth.py
│   ├── identity.py
│   ├── signal.py               # NormalizedSignal / SignalAction / NoiseFilterConfig
│   ├── bot.py                  # BotConfig
│   ├── billing.py
│   ├── rewards.py              # BalanceSnapshot
│   ├── withdrawals.py
│   └── admin/
├── routers/                    # HTTP 路由层（薄，只做参数校验与鉴权）
│   ├── v1/
│   │   ├── auth.py
│   │   ├── identity.py
│   │   ├── apikeys.py
│   │   ├── strategies.py
│   │   ├── bots.py
│   │   ├── subscriptions.py
│   │   ├── payments.py
│   │   ├── referrals.py
│   │   ├── rewards.py
│   │   ├── withdrawals.py
│   │   ├── account.py
│   │   └── ws.py              # /ws/stream
│   └── admin/
│       ├── users.py / review.py / signals.py / orders.py
│       ├── payments.py / invites.py / wallets.py / withdrawals.py
│       └── risk.py / audit.py
├── exchange_clients/           # 5 家交易所官方客户端（决策 B，自研）
│   ├── base.py                 # ExchangeAdapter 抽象 + 统一订单/余额/精度接口
│   ├── binance.py / okx.py / bybit.py / bitget.py / gate.py
│   ├── signing.py              # 各所签名（HMAC-SHA512/RSA/Ed25519）
│   ├── ratelimit.py            # 按接口分级限流 + 指数退避
│   └── ws_client.py            # 行情/成交/持仓变更 WS 订阅（心跳+重连）
├── services/                   # 21 个业务模块（核心逻辑，不依赖 HTTP）
│   ├── auth/
│   ├── identity/
│   ├── billing/
│   ├── payment/
│   ├── withdrawal/
│   ├── referral/
│   ├── ledger/
│   ├── apikeyvault/
│   ├── scraper/               # adapters（5 家交易所爬虫）
│   ├── normalizer/
│   ├── signalstore/
│   ├── copyengine/
│   ├── riskengine/
│   ├── executor/
│   ├── tradetracker/
│   ├── audit/
│   ├── mailer/
│   ├── notification/
│   └── observability/
├── workers/                    # Celery 任务（异步）
│   ├── celery_app.py
│   ├── tasks_signal.py         # 定时爬虫采集
│   ├── tasks_profile.py        # 每日画像同步（00:00-05:00）
│   ├── tasks_payment.py        # 支付轮询（1/5/10/20 min）
│   ├── tasks_reward.py         # 24h/48h 奖励核实释放
│   └── tasks_reminder.py       # 订阅到期/支付超时提醒
├── ws/                         # WebSocket Hub
│   ├── hub.py                  # 连接管理、房间订阅
│   ├── channels.py             # 8 个频道定义
│   └── handlers.py             # 各频道消息推送
├── tests/                      # 模块级单测（与 src 近置）
└── pyproject.toml              # 本包定义
```

---

## 4. 21 个业务模块与职责（对应设计 §3）

| # | 模块（包） | 核心类 | 主要职责 | 开发计划落点 |
|---|---|---|---|---|
| 1 | services/auth | AuthService | 注册/验证码/登录/改密/重置 | M1 T1.2 |
| 2 | services/identity | IdentityService | 选所/绑邀请/身份判定/PlatformPool 自动识别 | M1 T1.4 |
| 3 | services/billing | BillingService | 套餐/订阅生命周期/到期 | M4 T4.2 |
| 4 | services/payment | PaymentService | 三链支付/即时校验/轮询/手动确认 | M4 T4.3-T4.4 |
| 5 | services/withdrawal | WithdrawalService | 提现申请/审核/发放/链上校验 | M4 T4.6-T4.7 |
| 6 | services/referral | ReferralService | 邀请码/奖励触发判定/刷单检测 | M4 T4.5, T4.9 |
| 7 | services/ledger | LedgerService | 奖励账本/5 字段快照/冻结/回滚 | M4 T4.5 |
| 8 | services/apikeyvault | ApiKeyVault | API key AES-256-GCM 加密存取 | M1 T1.6 |
| 9 | services/scraper | AbstractScraperAdapter + Gate/GateAdapter | 5 所公开爬虫 | M2 T2.1 |
| 10 | services/normalizer | SignalNormalizer | 标准化/去重/噪声过滤/动作判定 | M2 T2.2 |
| 11 | services/signalstore | SignalStore | 信号落库/两级池/画像同步/门槛校验 | M2 T2.4-T2.7 |
| 12 | services/copyengine | CopyEngine | 跟单机器人/USDT 4 步换算/信号路由 | M3 T3.2-T3.4 |
| 13 | services/riskengine | RiskEngine | 5 条风控规则/延迟红线/邀请风控 | M3 T3.5 |
| 14 | services/executor | OrderRouter | 官方直连下单/滑点保护/杠杆保证金（经 ExchangeAdapter） | M3 T3.6 |
| 15 | services/tradetracker | TradeTracker | 成交回报/仓位对账/PnL | M3 T3.7 |
| 16 | services/audit | AuditService | 后台操作审计/审计日志 | M1 T1.10 |
| 17 | services/mailer | Mailer | SMTP 邮件（验证码/支付/提现） | M1 T1.3 |
| 18 | services/notification | NotificationService | 站内消息 WS 推送 | M1 T1.3 |
| 19 | services/observability | setup_logging/metrics/trace | 日志/指标/trace | M0 T0.8 |
| 20 | web-ui | Next.js App Router | 用户 SPA | M1/M2/M4/M5 |
| 21 | web-admin | Next.js App Router | 后台 10 模块 | M5 |

> 19 个后端模块 + 2 个前端 = 21 个核心模块，与设计文档 §3 完全对应。
> `exchange_clients/` 是基础设施组件（非业务模块），提供 5 家官方客户端，被 `executor` 与 `tradetracker` 调用。

---

## 5. 依赖注入与请求生命周期

### 5.1 服务容器

单个 `ServiceContainer` 在 app startup 时创建一次，持有全部服务实例与共享依赖（db session factory、redis、vault、ccxt 注册表），通过 FastAPI 依赖注入注入到路由。

```python
# api/deps.py
class ServiceContainer:
    def __init__(self, settings: Settings, engine, redis, vault):
        self.db = engine
        self.redis = redis
        self.vault = vault
        self.auth = AuthService(self.db, self.redis, self.vault)
        self.identity = IdentityService(self.db, self.audit)
        self.billing = BillingService(self.db, self.redis)
        self.payment = PaymentService(self.db, self.redis, self.rpc_clients)
        self.withdrawal = WithdrawalService(self.db, self.executor, self.mailer, self.notification)
        self.referral = ReferralService(self.db, self.ledger)
        self.ledger = LedgerService(self.db, self.audit)
        self.copy_engine = CopyEngine(self.db, self.risk, self.executor, self.trade_tracker)
        self.risk = RiskEngine(self.db, self.redis)
        # ... 其余服务

async def get_services(request) -> ServiceContainer:
    return request.app.state.services   # startup 时注入
```

### 5.2 路由依赖链

```
HTTP 请求 → 中间件(请求ID/限流/CORS) → get_services → get_current_user(鉴权)
  → router handler → 校验 Pydantic schema → 调用 service 方法 → 返回响应
```

### 5.3 模块间协作规则

- 同进程内：**函数调用**，服务通过容器互相引用（如 `copy_engine` 调 `risk.evaluate`）。
- 异步解耦：信号采集、画像同步、支付轮询、奖励释放走 **Celery 任务**。
- 实时事件：信号/订单/奖励变更写 **Redis Pub/Sub**，由 WS Hub 订阅后推给前端。

---

## 6. 数据层设计

### 6.1 单库原则

全部业务表落在 **PostgreSQL 单库**（信号、订单、画像、账本、审计）。TimescaleDB、对象存储、独立时序库**不引入**（数据量未达阈值）。

### 6.2 ORM 与迁移

- SQLAlchemy 2.0 async，模型定义在 `api/models/`（对应设计 §4.2 全部表）。
- Alembic 管理迁移，`alembic upgrade head` 在容器启动时执行。
- 关键唯一约束：邮箱 CITEXT UNIQUE、`Identity(exchange,user_id)`、`SourceSignal.dedupe_key`、`ContractSpec(exchange,symbol)`、`PlatformPool.invite_code`、`TraderProfile(trader_id,snapshot_date)`。

### 6.3 事务边界

每个 service 方法一个事务；跨模块动作（如支付确认→激活订阅→触发奖励）用**独立事务 + 补偿**，同表更新依赖唯一约束防重。

---

## 7. 配置管理

- 用 `pydantic-settings` 读取环境变量，集中在 `api/core/config.py`。
- 所有变量在 `.env.example` 留有模板，实际值由部署环境注入。
- 敏感项：`MASTER_KEY_B64`（凭证主密钥）、各交易所/区块链接口凭据、数据库/Redis 连接串。
- 启动校验：`MASTER_KEY_B64` 缺失或长度错误时进程拒绝启动，日志禁止输出密钥明文。

---

## 8. Celery 异步任务

| 任务 | 触发 | 队列 |
|---|---|---|
| 爬虫采集（模式 A） | Celery Beat 定时 | signal |
| 每日画像同步（00:00-05:00 全量） | Celery Beat | profile |
| 支付确认轮询（1/5/10/20 min） | 轮询调度 | payment |
| 奖励核实释放（24h/48h 到期） | 定时扫 | reward |
| 订阅到期扫描 | 定时 | reminder |
| 邮件发送 | 事件入队 | mail |

---

## 9. WebSocket Hub

- 单一入口 `/ws/stream`，JWT 鉴权后建立连接。
- 连接按 `user_id` 归入房间，订阅 8 个频道：`strategy.update`、`signal.new`、`bot.position`、`bot.order`、`pnl.tick`、`account.balance`、`reward.tick`、`withdrawal.status`。
- 服务打点写入 Redis Pub/Sub，Hub 消费后定向推送；离线用户下次连接拉取未读站内消息。

---

## 10. 前端结构

### 10.1 web-ui（用户前台）

```
web-ui/
├── app/
│   ├── (marketing)/page.tsx          # 首页（4 卡 + 新手引导 + 眼睛隐藏）
│   ├── (auth)/login/page.tsx
│   ├── (auth)/register/page.tsx
│   ├── strategies/page.tsx           # 策略广场（M2）
│   ├── strategies/[id]/page.tsx      # 策略详情（M2）
│   ├── bots/page.tsx                 # 我的跟单（M3）
│   ├── account/page.tsx              # 个人中心
│   ├── account/apikeys/page.tsx      # 我的 API
│   ├── invite/page.tsx               # 邀请中心
│   ├── rewards/page.tsx              # 奖励余额（5 字段）
│   ├── withdraw/page.tsx             # 提现申请
│   └── layout.tsx
├── components/{StrategyCard,BotCard,RewardTable,WithdrawalForm,ApiKeyForm,AddressInput}.tsx
├── lib/{api.ts,ws.ts}                # REST client + WS client
└── stores/{useAuth,useBots,useRewards}.ts
```

### 10.2 web-admin（后台，与前台完全隔离）

```
web-admin/
├── app/
│   ├── login/page.tsx
│   ├── dashboard/page.tsx
│   ├── users/{page,detail/[id]}.tsx
│   ├── review/page.tsx               # 主号下级审核
│   ├── signals/{page,[exchange]/page,detail/[id]}.tsx
│   ├── orders/page.tsx
│   ├── payments/page.tsx
│   ├── invites/page.tsx
│   ├── wallets/page.tsx
│   ├── withdrawals/page.tsx
│   ├── risk/page.tsx
│   └── audit/page.tsx
├── lib/{api.ts,auth.ts}
└── stores/{useAdminAuth,useOrders,useWithdrawals}.ts
```

隔离约束：独立登录入口、独立 cookie 名与 JWT audience、写接口强制写 audit-log、RBAC 双层权限。

> ✅ **后台 UI 成品已交付（2026-08-12）**：11 个页面全部完成（后台登录 / 数据概览 / 用户管理 / 信号源审核 / 跟单订单 / 支付记录 / 邀请奖励 / 钱包账本 / 提现审核 / 风控中心 / 审计日志），红色 ADMIN 设计语言 + 信号宇宙背景，全部互链。入口：[后台页面导航索引](./2026-08-12-signal-saas-admin-index.html)。上述 `web-admin/app/` 骨架全部有成品实现，可直接作为 M5 开发视觉蓝本。

---

## 11. 测试结构

```
tests/
├── conftest.py               # 共享 fixtures（内存 PG、mock ccxt、测试 Redis）
├── unit/                     # 单测（换算/风控/画像/账本/加密）
├── integration/              # 接口测试（注册→支付→跟单→提现 全链路）
└── e2e/                      # 端到端（可选，M6 前）
```

关键单测项（来自开发计划 DoD）：USDT 4 步换算（合约级精度）、5 条风控规则（含 action 路由）、8 类失败归因、门槛校验(force/force_skip)、48h 延长核实、5 字段余额快照。

---

## 12. 部署结构（Docker Compose）

```
services:
  api:        # FastAPI + uvicorn（多 worker），healthz/readyz
  worker:     # Celery worker（消费 signal/profile/payment/reward/mail 队列）
  beat:       # Celery Beat 调度
  web-ui:     # Next.js 用户前台
  web-admin:  # Next.js 后台
  postgres:   # PG 15，数据卷持久化
  redis:      # Redis 7，AOF
  prometheus: # 采集 /metrics
  grafana:    # 看板
  nginx:      # 反代 + TLS 终止
```

启动流程：`docker compose up -d` → PG/Redis 就绪 → `alembic upgrade head` → api/worker/beat 起 → 前端构建起服务。

---

## 13. 与开发计划 M0 的对应落实

| 框架元素 | M0 落点 | 需调整 |
|---|---|---|
| `api/` 单体目录（§3） | T0.3 FastAPI 骨架 | 替换旧"21 模块平铺"骨架 |
| 配置/密钥校验（§7） | T0.5/T0.6 凭证保险库 | 一致 |
| 监控可观测（§3.19） | T0.8 | 一致 |
| Docker Compose（§12） | T0.2 | 移除旧微服务编排 |
| 双前端（§10） | T0.4 | 一致 |
| CI（§11） | T0.7 | 一致 |

---

## 14. 高并发与信号扩展设计

> 实际约束：后期需监控大量信号源并驱动大量跟单机器人，压力集中在**信号采集/处理（fan-out）**，而非用户 HTTP 层。本单休架构通过**多进程 worker 池 + Redis 缓冲 + 批量写库 + 分区队列**横向扩展，代码无需改动。

### 14.1 容量估算（量化高并发）

| 参数 | 保守 | 高频 | 说明 |
|---|---|---|---|
| 监控信号源 | 2000 带单员 | 5000 | 后台两级池可承载 |
| 单员动作频率 | 1 次/60s | 1 次/15s | 开/加/减/平 |
| 信号产生 | 33 信号/秒 | 333 信号/秒 | 经标准化/去重后 |
| 平均 fan-out | 3 | 5 | 每信号触发 bot 数 |
| bot 动作处理 | ~100/秒 | ~1665/秒 | 需写 CopyOrder + 快照 |

单进程 FastAPI 信号链路（标准化+去重+路由+风控）为内存运算，异步单核可处理数千信号/秒，**远超高频需求**。真正瓶颈是**写库**，用批量写解决（见 14.3）。

### 14.2 部署进程拓扑（同一套代码，多进程）

```
signal-saas/  (同一份代码)
├── api         × N   # 用户 HTTP + WS（uvicorn workers，常规负载）
├── worker-fanout × N # 信号 fan-out 消费（独立队列，CPU 密集可加进程）
├── worker-daemon× N  # 画像同步 / 支付轮询 / 奖励释放 / 邮件
├── worker-scrape × N # 信号采集（爬虫，代理池）
└── beat              # Celery Beat 调度
```

- 信号先写 **Redis Stream**（`signal.{exchange}`）缓冲削峰，独立 worker 池消费。
- **按交易所分区队列**：`signal.{exchange}`，避免单一消费热点，可各自扩展。
- 需求翻倍时新增对应 worker 进程即可，**不改代码**。

### 14.3 批量写库

- `CopyOrder` / `PositionSnapshot` 用 **500ms 窗口批量 flush**（`executemany`），把写库吞吐提升一个数量级。
- 高频信号在内存聚合后定时落库，减少行锁竞争。
- 索引按 `(exchange, symbol, opened_at)`、`(bot_id, status)` 设计，支撑查询而不过度膨胀。

### 14.4 扩展边界与上限

- PostgreSQL 单库行量：信号/订单为百万级/月，单机 PG 足够；超量时按月份**分区表**扩展（V1 已设计分区承载）。
- 采集并发：受交易所反爬与代理池容量约束，是**外置瓶颈**，与框架无关。
- WS 连接：单机 uvicorn 可支撑数千长连接，超限时 api 进程横向加核即可。

---

## 15. 待办与后续

- [x] 将框架 `api/` 目录结构回写开发计划 §1.3（替换旧骨架）——已完成。
- [x] 将设计文档 §2.1 架构图更新为单体版——已完成。
- [x] 新增高并发与信号扩展设计（§14）——已完成。
- [x] 前台 8 个成品页面 + 前台导航索引（UI 框架 v0.1 / 交互 v0.2 / 补充 v0.3）——已完成。
- [x] 后台 11 个成品页面（登录 + 10 模块） + 后台导航索引——已完成（2026-08-12）。
- [x] ★G27 交易所邀请码管理：设计（ExchangeInviteCode 表 + verify_and_bind）+ 前端注册引导 + 后台管理页——已完成（2026-08-12）。
- [x] 开发前全面检查：三文档交叉核对 + UI 路由覆盖 + G09/G27 回写 + 前台 account 页 + 后台 review 页补缺——已完成（2026-08-12）。
- [ ] 按框架 §3 生成全部目录与空模块（M0 触发）。
- [ ] 用框架 §14 的分区队列/批量写库指导 M2/M3 具体实现。
- [x] 把 UI 成品（前台 8 页 + 后台 11 页）作为 M5 开发视觉蓝本，回写开发计划 M5 任务——已完成（2026-08-12，M5 §6.2/6.3 逐任务标注蓝本链接）。