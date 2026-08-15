# 加密货币信号源聚合平台 开发框架规划

> 文档定位：仅做"框架骨架 + 接口契约 + 通信契约"，不写实现细节；每个文件给出接口签名 + 关键 TODO。
> 用户已确认参数：5 大主流 CEX × 3 种采集方式（混合） × 全自动跟单 × 完全独立新项目 × 只搭框架。

---

## 0. 调研结论摘要

### 0.1 五家 CEX 跟单能力对照

| 交易所 | 官方跟单 API | 协议类型 | 鉴权要求 | 限制/备注 |
|---|---|---|---|---|
| Binance | 有（`/sapi/v1/copyTrading/*`，Lead 子账户 API key 自动触发复制） | REST + 私有 WebSocket（userDataStream） | Lead 子账户 API key + secret | 部分地区受限，Futures Copy Trading 用户可"通过 API 下单，自动触发复制" |
| OKX | 有（`/api/v5/copytrading/*`，含现货/合约/配置/通知） | REST 为主 + WebSocket（白名单） | API key + secret + passphrase | 通知频道 `ws.CopyTrading` 需白名单；初始可走 REST 轮询 |
| Bybit | 有（`/v5/copyTrading/*`，Master/Follower 双接口） | REST + 私有 WebSocket（position/order/execution） | API key + secret | Leaderboard 公开；私有持仓需鉴权 |
| Bitget | 有（`/api/v2/copy/*` 与 `/api/v3/copy/*`，mix/spot follower 与 trader 四套子接口） | REST + 私有 WebSocket | API key + secret + passphrase | 通过 `paptrading: 1` 头切换模拟盘 |
| Gate.io | 有（`/api/v4/copy/*`） | REST 为主 + WebSocket（quant 业务端点） | API key + secret | v2/v4 共存，统一以 v4 为准 |

来源：Binance Developer Community [dev.binance.vision/t/21984](https://dev.binance.vision/t/how-to-place-order-as-a-copy-trading-leader/21984)；OKX V5 API changelog [okx docs-v5/log_en](https://hk.okx.com/docs-v5/log_en/)；Bitget 端点清单 [tiagosiebler/bitget-api](https://github.com/tiagosiebler/bitget-api/blob/master/docs/endpointFunctionList.md) 与 v2 release note [glassgs](https://www.glassgs.com/zh-CN/api-doc/common/release-note)；Gate.io v4 [gate.com APIv4](https://www.gate.com/docs/developers/apiv4/zh_CN/)。

### 0.2 ccxt 库覆盖范围

- ccxt 已支持全部五家交易所的统一行情/下单/账户接口，但**不包含跟单（Copy Trading）的统一抽象** —— 跟单 endpoint 必须各家自实现。
- 结论：用 `ccxt` 做"统一行情 + 统一跟单下单"（用户侧执行）；自研 `adapter` 层做"五种采集策略"。

### 0.3 开源参考的借鉴点

- **Freqtrade**：分层架构、ccxt 抽象、SQLite/PG 持久化、Telegram/Rest/WebUI 控制面。借鉴其"策略 interface"做信号评分 Strategy。
- **ccxt-social-trader / Hummingbot strategy-v2**：消息总线 + 多策略并行编排。
- **NautilusTrader**：事件驱动 + MessageBus 模型作为 `signal-bus` 设计蓝本。
- **关键差异**：本项目是"多源信号聚合 + 多用户跟单执行" SaaS 中枢，需要用户级密钥保险库与多租户风控，Freqtrade 不覆盖。

---

## 1. 架构总览（文字版）

```
                          +-------------------------+
                          |       Next.js 14         |
                          |  App Router + shadcn     |
                          |  (web-ui)                |
                          +-----------+--------------+
                                      | REST / WS
                          +-----------v--------------+
                          |   FastAPI (web-api)      |
                          |  REST + WebSocket Gateway |
                          +-----+----------+---------+
                                |          |
                  +-------------v-+      +-v--------------+
                  |  Config/Auth  |      |  Observability |
                  +-------+-------+      +-------+--------+
                          |                      |
+------------------+   +---v----+    +----------v---------+    +------------------+
| exchange-adapters|<->| signal |    |     signal-store    |    |     risk-engine  |
| (5 家 × 3 策略)  |   | -normal|    |  PG / TimescaleDB  |    |  白名单/限额/制动 |
+--------+---------+   |  izer  |    |  / Redis Cache     |    +---------+--------+
         |             +----+---+    +--------------------+              |
         |                  |                                              |
+--------v---------+   +----v-----+                                 +-------v-------+
| signal-collector |-->| signal- |---- Redis Streams ------------>|    executor    |
| 多策略调度/速率  |   |   bus   |     (events.standard.*)         |  ccxt 下单+保险|
| 断点续采/代理池  |   +----+----+                                  +-------+-------+
+------------------+        |                                               |
                       +----v-----+                                  +-------v-------+
                       | trade-   |  <-- ws/REST 成交回报 ---------| trade-tracker  |
                       | tracker  |                                 | 信号-成交对账  |
                       +----+-----+                                 +-------+-------+
                            |                                             |
                       +----v-----+                                +------v--------+
                       |  notif.  |                                |  Redis Stream |
                       |  TG/DC/  |                                |  (events.exe.*)|
                       |  Webhook |                                +------+---------+
                       +----------+                                       |
                                                                  +-------v------+
                                                                  |  notification|
                                                                  +--------------+
```

### 模块边界契约

- `signal-collector` → `signal-bus`：仅产 `RawSignal`（未归一化）。
- `signal-normalizer` → `signal-bus`：产 `NormalizedSignal`（统一 schema）。
- `signal-bus` → `risk-engine`：触发 `RiskEvalRequest`，产出 `RiskDecision`。
- `risk-engine` → `executor`：通过 `signal-bus` 发 `OrderIntent`。
- `executor` → `trade-tracker`：发 `ExecutionReport`；`trade-tracker` 发 `PositionUpdate`。
- `web-api` 是唯一对外 HTTP/WS 入口，所有内部事件不直接暴露。

---

## 2. 模块划分与文件骨架

### 2.1 exchange-adapters/（适配器层）

```
exchange-adapters/
├── __init__.py
├── base/
│   ├── adapter.py                # AbstractExchangeAdapter
│   ├── strategy_official.py      # AbstractOfficialCopyAdapter
│   ├── strategy_leaderboard.py   # AbstractLeaderboardAdapter
│   └── strategy_mini_account.py  # AbstractMiniAccountAdapter
├── binance/{official,leaderboard,mini_account}.py
├── okx/{official,leaderboard,mini_account}.py
├── bybit/{official,leaderboard,mini_account}.py
├── bitget/{official,leaderboard,mini_account}.py
├── gate/{official,leaderboard,mini_account}.py
└── tests/
```

**关键接口（`base/adapter.py`）**：

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Literal
from datetime import datetime
from pydantic import BaseModel

class AdapterContext(BaseModel):
    exchange: Literal["binance","okx","bybit","bitget","gate"]
    proxy: str | None = None
    rate_limit: float = 5.0
    timeout: float = 10.0
    credential_ref: str | None

class RawSignal(BaseModel):
    exchange: str
    source: Literal["official","leaderboard","mini"]
    trader_id: str
    symbol: str
    side: Literal["long","short","buy","sell"]
    leverage: float | None
    qty: float | None
    entry_price: float | None
    sl: float | None
    tp: float | None
    opened_at: datetime
    raw: dict
    trace_id: str

class AbstractExchangeAdapter(ABC):
    exchange: str
    def __init__(self, ctx: AdapterContext): ...
    @abstractmethod
    async def health(self) -> bool: ...
    @abstractmethod
    async def fetch_signals(self, since: datetime | None = None,
                            cursor: str | None = None
                            ) -> AsyncIterator[RawSignal]: ...
    @abstractmethod
    async def resolve_trader(self, trader_id: str) -> dict: ...

class AbstractOfficialCopyAdapter(AbstractExchangeAdapter):
    """官方跟单 API：通过 Lead 子账户/专属 API key 拉取关注者自动复制后的成交。"""
    @abstractmethod
    async def list_followers(self) -> list[dict]: ...
    @abstractmethod
    async def fetch_copy_orders(self, follower_id: str, since: datetime | None) -> AsyncIterator[RawSignal]: ...

class AbstractLeaderboardAdapter(AbstractExchangeAdapter):
    """公开排行榜爬虫：抓取平台公开页（Playwright/直连 API），解析交易员开仓。"""
    @abstractmethod
    async def fetch_top_traders(self, period: str = "30d", limit: int = 100) -> list[dict]: ...
    @abstractmethod
    async def fetch_trader_positions(self, trader_id: str) -> AsyncIterator[RawSignal]: ...

class AbstractMiniAccountAdapter(AbstractExchangeAdapter):
    """小号跟单 API：注册专用 Lead 小号→绑 Leader→订阅 WebSocket 推送成交。"""
    @abstractmethod
    async def register_mini(self) -> dict: ...
    @abstractmethod
    async def bind_leader(self, leader_id: str) -> None: ...
    @abstractmethod
    async def stream_mini_fills(self) -> AsyncIterator[RawSignal]: ...  # WS
```

各交易所实现关键 TODO（统一模板）：

```python
class BinanceOfficialCopyAdapter(AbstractOfficialCopyAdapter):
    """TODO: 调用 /sapi/v1/copyTrading/futures/leadTradeList 等接口；
    使用 Binance Lead Copy 子账户的 API key + secret 拉取关注者成交；
    私有 channel 用 userDataStream（listenKey）。"""
    BASE = "https://api.binance.com"
```

- **OKX**：`/api/v5/copytrading/...` 走 REST；通知频道需白名单，初期走"轮询 lead 当前持仓"。
- **Bybit**：`/v5/copyTrading/...` + 私有 WS topic `position`/`order`。
- **Bitget**：`/api/v2/copy/mix-trader/...`、`/api/v3/copy/futures/...`，私有 WS `wss://ws.bitget.com/v2/ws/private`。
- **Gate.io**：`/api/v4/copy/...`；v2 与 v4 共存，统一以 v4 为准。

### 2.2 signal-collector/（采集调度）

```
signal-collector/
├── scheduler.py          # CollectorScheduler：多策略并发、断点续采
├── ratelimiter.py        # TokenBucket / SlidingWindow
├── proxy_pool.py         # IP 代理池 + 健康检查
├── backoff.py            # 指数退避 + 抖动
├── checkpoint.py         # 基于 Redis 的游标/时间戳 checkpoint
└── pipeline.py           # CollectorPipeline：编排（adapter → normalizer → bus）
```

```python
class CollectorPipeline:
    def __init__(self, adapter, checkpoint, bus, rate_limiter, proxy_pool): ...
    async def run_forever(self) -> None: ...
    async def _tick_once(self) -> int: ...
    # TODO: 实现 backoff、断点续采、失败上报 Prometheus counter
```

### 2.3 signal-normalizer/（标准化）

```
signal-normalizer/
├── model.py              # NormalizedSignal
├── parser.py             # 五家 × 三策略的解析器注册表
├── dedupe.py             # 信号去重（交易所+交易员+symbol+方向+opened_at 二级指纹）
└── enricher.py           # 标注 leverage tier / 资金费率 / 标记价
```

```python
class NormalizedSignal(BaseModel):
    signal_id: str               # 全局 UUID v7
    exchange: str
    source: str                  # official|leaderboard|mini
    trader_id: str
    trader_name: str | None = None
    symbol: str                  # ccxt 统一格式 BTC/USDT:USDT
    market: Literal["spot","swap","future"]
    side: Literal["open_long","open_short","close_long","close_short"]
    leverage: float
    qty: float
    notional_usd: float | None
    entry_price: float | None
    mark_price: float | None
    sl: float | None
    tp: list[float]
    opened_at: datetime
    received_at: datetime
    confidence: float            # 0~1
    raw_ref: str                 # 指向原始 payload 的存储 key
```

### 2.4 signal-store/（存储层）

```
signal-store/
├── models/{orm.py, ts.py}    # SQLAlchemy 2.x async 模型 + TimescaleDB hypertable
├── migrations/                # Alembic
├── archive.py                 # 按月分区/冷归档到 S3/MinIO
└── cache.py                   # Redis 最近信号缓存
```

表骨架：

```sql
CREATE TABLE trader (
  id BIGSERIAL PRIMARY KEY,
  exchange TEXT NOT NULL,
  trader_id TEXT NOT NULL,
  display_name TEXT,
  meta JSONB,
  UNIQUE(exchange, trader_id)
);

CREATE TABLE signal (
  id BIGSERIAL PRIMARY KEY,
  signal_id UUID UNIQUE NOT NULL,
  exchange TEXT NOT NULL,
  source TEXT NOT NULL,
  trader_id BIGINT REFERENCES trader(id),
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  side TEXT NOT NULL,
  leverage NUMERIC,
  qty NUMERIC,
  notional_usd NUMERIC,
  entry_price NUMERIC,
  sl NUMERIC,
  tp NUMERIC[],
  opened_at TIMESTAMPTZ NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  raw_ref TEXT,
  dedupe_key TEXT UNIQUE  -- exchange|trader|symbol|side|opened_at
);
CREATE INDEX ON signal (exchange, symbol, opened_at DESC);
CREATE INDEX ON signal (trader_id, opened_at DESC);

-- TimescaleDB hypertable：K 线
SELECT create_hypertable('kline_1m', 'ts', if_not_exists => TRUE);
```

### 2.5 risk-engine/（风控）

```
risk-engine/
├── engine.py              # RiskEngine：编排白名单、限额、并发、日亏
├── rules/{whitelist,position_limit,concurrency,daily_loss,emergency_stop}.py
└── context.py             # 用户/账户/策略上下文
```

```python
class RiskDecision(BaseModel):
    approved: bool
    reason: str | None = None
    modified_intent: OrderIntent | None = None

class RiskEngine:
    async def evaluate(self, user_id: int,
                       signal: NormalizedSignal,
                       intent: OrderIntent) -> RiskDecision: ...
```

> 用户只要求"搭框架"，风控规则具体阈值留 `TODO: ...`。

### 2.6 executor/（下单执行）

```
executor/
├── vault.py               # ApiKeyVault：AES-GCM 加密保险库
├── ccxt_client.py         # ccxt 工厂，支持五家
├── order_router.py        # 滑点/重试/拆单
├── mini_account_pool.py   # 跟单小号池
└── retry.py               # 错误分类：可重试 vs 终态
```

```python
class ApiKeyVault:
    def __init__(self, master_key: bytes): ...
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...

class OrderRouter:
    async def place(self, intent: OrderIntent, user_ctx: UserContext) -> ExecutionReport: ...
    # TODO: 限价单保护价 = 信号价 * (1 ± slippage_bps/1e4)
    # TODO: 失败分类：429/5xx 重试；4xx 业务错误不重试
```

**加密方案（必须落库前实现）**：

- 算法：`AES-256-GCM`，`nonce=12B`、`tag=16B`。
- 主密钥：经环境变量 `MASTER_KEY_B64` 注入；KMS 留接口。
- 数据库列：仅存密文与 `key_id`，禁止明文日志。
- 备份：HMAC-SHA256 校验和。

### 2.7 trade-tracker/（成交跟踪）

```
trade-tracker/
├── ws_listener.py         # 各交易所私有 WS 适配
├── position.py            # 仓位聚合
├── pnl.py                 # 已实现/未实现盈亏
├── reconciliation.py      # 信号-成交对账
└── attribution.py         # 归因到具体 signal_id
```

### 2.8 notification/（通知）

```
notification/
├── base.py                # Notifier ABC
├── telegram.py
├── discord.py
├── webhook.py
├── email.py
└── router.py              # NotificationRouter
```

### 2.9 web-api/（FastAPI 接口层）

```
web-api/
├── main.py
├── deps.py                # Depends 注入
├── routers/{signals,traders,accounts,orders,risk,ws}.py
├── schemas/
└── auth/
```

**REST 端点骨架**：

| Method | Path | 说明 |
|---|---|---|
| GET | /v1/signals | 信号流（分页/筛选） |
| GET | /v1/traders | 交易员列表+评分 |
| GET | /v1/traders/{id}/positions | 当前持仓 |
| POST | /v1/accounts | 绑定交易所 API key（加密落库） |
| POST | /v1/accounts/{id}/follow | 启用/调整跟单 |
| POST | /v1/orders/{id}/cancel | 撤单 |
| GET | /v1/risk/limits | 当前风控限额 |
| WS | /ws/stream | 实时推送信号/成交/风控事件 |

### 2.10 web-ui/（Next.js）

```
web-ui/
├── app/
│   ├── (dashboard)/{signals,traders,risk,settings}/page.tsx
│   └── layout.tsx
├── components/{SignalStream,PnLChart,TraderScorecard,RiskPanel}.tsx
├── lib/{api,ws}.ts
└── styles/
```

### 2.11 config/（配置中心）

```
config/
├── settings.py            # Pydantic Settings
├── secrets.py             # AES 主密钥管理
├── loader.py              # YAML + env 覆盖
└── schemas/
```

```python
class Settings(BaseSettings):
    env: Literal["dev","staging","prod"]
    redis_url: str
    pg_dsn: str
    timescaledb_dsn: str
    master_key_b64: str
    exchanges_enabled: list[str]
    rate_limits: dict[str, float]
    proxy_pool: list[str]
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")
```

### 2.12 observability/（可观测）

```
observability/
├── logging.py             # 结构化日志
├── metrics.py             # Prometheus client
├── tracing.py             # OpenTelemetry
└── health.py              # /healthz, /readyz
```

关键指标：`signals_received_total{exchange,source}`、`signals_normalized_total{exchange}`、`risk_decisions_total{decision}`、`orders_placed_total{exchange,result}`、`executor_latency_seconds{exchange}`、`collector_lag_seconds{exchange,source}`。

### 2.13 tests/（测试体系）

```
tests/
├── unit/                  # pytest + pytest-asyncio
├── integration/           # docker-compose 起依赖
├── e2e/                   # Playwright
├── fixtures/{mock_exchanges,payloads}
└── conftest.py
```

---

## 3. 模块间通信契约（事件 Schema & Topic）

### 3.1 消息总线：Redis Streams

**Topic 命名规范**：`{domain}.{entity}.{action}.v{ver}`

| Topic | Payload | Producer | Consumer |
|---|---|---|---|
| `signal.raw.received.v1` | `RawSignal` | collector | normalizer |
| `signal.normalized.v1` | `NormalizedSignal` | normalizer | risk-engine, web-api 缓存 |
| `signal.duplicate.v1` | `{signal_id, dedupe_key}` | normalizer | observability |
| `risk.decision.v1` | `RiskDecision` | risk-engine | executor, notification |
| `order.intent.v1` | `OrderIntent` | risk-engine | executor |
| `order.placed.v1` | `ExecutionReport` | executor | trade-tracker, web-api |
| `order.failed.v1` | `ExecutionReport{status=failed}` | executor | notification, trade-tracker |
| `position.update.v1` | `PositionSnapshot` | trade-tracker | web-api, notification |
| `trader.score.v1` | `TraderScore` | trade-tracker | web-api |

事件顶层字段：

```json
{
  "event_id": "0190f7c2-...-v7",
  "event_time": "2026-08-11T08:32:11.221Z",
  "trace_id": "req:abc123",
  "schema_version": 1,
  "payload": { "...": "..." }
}
```

**消费组（Consumer Group）**：

- `grp.normalizer` 消费 `signal.raw.*`
- `grp.risk` 消费 `signal.normalized.*`
- `grp.executor` 消费 `order.intent.*`
- `grp.tracker` 消费 `order.placed.*` 与 `order.failed.*`

### 3.2 Schema 版本化

- 每条事件顶层带 `schema_version`，payload 变更必须增版本。
- 当前阶段可先用 Pydantic + 校验，未来可引入 Avro/JSON Schema。

---

## 4. 数据流（端到端）

1. 调度器触发 `CollectorPipeline.run_forever()`：选 adapter + 读 `checkpoint` 游标 → `proxy_pool` 取代理 → `RateLimiter` 限流 → 拉 `RawSignal` → 写 `signal.raw.received.v1`。
2. `signal-normalizer` 消费 → 解析 → 计算 `dedupe_key` → 写库 → 发 `signal.normalized.v1`。
3. `risk-engine` 消费 → 注入 `OrderIntent` → 发 `order.intent.v1`。
4. `executor` 消费 → 解密用户密钥 → ccxt 下单 → 发 `order.placed/failed.v1`。
5. `trade-tracker` 消费 + 监听私有 WS → 更新 `PositionSnapshot` → 发 `position.update.v1`。
6. `web-api` 通过 Redis 缓存/WS 网关广播给 `web-ui`；`notification` 按用户偏好路由。

---

## 5. 配置项（YAML + 环境变量）

`config/app.yaml`：

```yaml
env: dev
exchanges:
  binance: { enabled: true, base_url: https://api.binance.com, ws_url: wss://stream.binance.com:9443/ws, rate_limit: 10, sources: [official, leaderboard, mini] }
  okx:     { enabled: true, base_url: https://www.okx.com, ws_url: wss://ws.okx.com:8443/ws/v5, sources: [official, mini] }
  bybit:   { enabled: true, base_url: https://api.bybit.com, ws_url: wss://stream.bybit.com/v5/private, sources: [official, leaderboard, mini] }
  bitget:  { enabled: true, base_url: https://api.bitget.com, ws_url: wss://ws.bitget.com/v2/ws/private, sources: [official, leaderboard, mini] }
  gate:    { enabled: true, base_url: https://api.gateio.ws/api/v4, sources: [official, leaderboard] }
collector:
  concurrency: 5
  backoff_initial_ms: 500
  backoff_max_ms: 30000
proxy_pool: []
risk:
  max_concurrent_orders: 5
  max_daily_loss_usd: 1000
  max_single_notional_usd: 5000
notification:
  telegram:
    enabled: true
    bot_token_env: TG_BOT_TOKEN
  webhook:
    enabled: false
```

环境变量优先级：`APP_*` > `.env` > `app.yaml`。

---

## 6. 技术风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| OKX 跟单通知 WS 需白名单 | 无法实时接收 Lead 成交 | 退化为轮询 REST `copytrading/...`；或申请白名单 |
| Bitget mini-account WS 频繁断线 | 数据延迟 | 加重连 + 游标续采；订阅 backup endpoint |
| Gate.io v2/v4 接口共存 | 调用错端点 | 强制 base URL + 端点注册表 + 集成测试断言 |
| 公开排行榜爬虫反爬 | 数据缺失 | Playwright + 代理池 + 频率分散；退化为官方 Leaderboard API |
| 用户 API key 泄漏 | 资产损失 | AES-256-GCM + KMS + IP 白名单 + 仅授信读写/交易、禁用提币 |
| 信号延迟导致滑点 | 跟单亏损 | 限价单 + 价格偏离阈值 + 撤单重挂 |
| 多源信号重复 | 重复跟单 | `dedupe_key` UNIQUE + 二级指纹（symbol+side+opened_at±2s） |
| ccxt 行为差异 | 跨所执行不一致 | `ccxt_client.py` 抽象 `safe_create_order` + 单元测试覆盖 |
| TimescaleDB 高基数 | 写入慢 | 按周分区 + 压缩策略 + 冷数据归档到对象存储 |
| 风控规则误伤 | 漏单 | 灰度发布 + 回滚 + 规则 dry-run 模式 |

---

## 7. 与 gate_copy_trading 项目的差异

| 维度 | gate_copy_trading（推测） | 本框架 |
|---|---|---|
| 交易所覆盖 | 单一 Gate.io | 5 家 CEX 同等支持 |
| 采集策略 | 1 种 | 3 种并行（官方+排行榜+小号） |
| 用户模型 | 单用户/单密钥 | 多租户 + 密钥保险库 |
| 信号聚合 | 无 | 多源信号归一、去重、评分 |
| 风控 | 基础止损 | 白名单+限额+并发+日亏+紧急制动 |
| 跟单触发 | 实时同步 | 异步（Redis Streams + Celery） |
| UI | 无 / 命令行 | Next.js 实时看板 |
| 可观测性 | 基础日志 | Prometheus + OTel + 结构化日志 |
| 数据存储 | 内存或单库 | PG + TimescaleDB + Redis 三层 |
| 部署 | 单脚本 | Docker Compose → k8s 平滑迁移 |

**可参考借鉴点**：

- Gate.io 鉴权/签名逻辑（HMAC-SHA512）作为本项目 `gate` adapter 的参考实现；
- 若 `gate_copy_trading` 已实现"小号订阅 Lead WS"，可参考其重连/序列号/心跳设计。

---

## 8. 启动顺序（本地一键起）

`docker-compose.yml` 骨架：

```yaml
services:
  postgres:    { image: timescale/timescaledb:latest, ports: ["5432:5432"] }
  redis:       { image: redis:7-alpine, ports: ["6379:6379"] }
  api:         { build: ./web-api, depends_on: [postgres, redis] }
  collector:   { build: ./signal-collector, depends_on: [postgres, redis] }
  normalizer:  { build: ./signal-normalizer, depends_on: [postgres, redis] }
  risk:        { build: ./risk-engine, depends_on: [postgres, redis] }
  executor:    { build: ./executor, depends_on: [postgres, redis] }
  tracker:     { build: ./trade-tracker, depends_on: [postgres, redis] }
  notifier:    { build: ./notification, depends_on: [redis] }
  web:         { build: ./web-ui, depends_on: [api] }
  prometheus:  { image: prom/prometheus, ports: ["9090:9090"] }
  grafana:     { image: grafana/grafana, ports: ["3000:3000"] }
```

启动顺序（Makefile 目标）：

1. `make infra-up`：拉起 postgres+timescale、redis
2. `make migrate`：跑 Alembic 迁移 + TimescaleDB hypertable 创建
3. `make run-api`、`make run-collector` ... 各 worker 并行
4. `make run-web`：Next.js dev server
5. `make health`：自动检测 `/healthz` 全部绿

---

## 9. 迭代路线（分阶段交付）

### 阶段 0：脚手架（当前任务产出）

- 13 个模块的目录骨架与接口签名（本文档）
- docker-compose 最小集
- 事件 schema v1（Pydantic 定义）
- CI（lint + 单测空跑）

### 阶段 1：单交易所闭环（MVP1）

- 选 Binance（官方跟单 API + mini account WS）
- collector→normalizer→risk→executor→tracker→web-api→web-ui 全链路
- 单租户、仅 spot/swap 跟单、基础风控

### 阶段 2：多交易所并行（MVP2）

- 加入 OKX、Bybit
- 加入排行榜爬虫（Playwright）+ 代理池
- 多用户 + 密钥保险库 + 通知
- TimescaleDB 上线

### 阶段 3：剩余交易所与高级能力（MVP3）

- 加入 Bitget、Gate.io
- 信号评分 + Trader 排行榜
- 紧急制动、回放回测

### 阶段 4：SaaS 化

- 鉴权/计费/审计
- 多租户隔离、数据库分片
- k8s 部署 + 自动伸缩
- 合规：KMS、密钥轮换、敏感操作二次确认

---

## 10. 接口签名速查（精选）

```python
# exchange-adapters/base/adapter.py
class AbstractExchangeAdapter(ABC):
    async def health(self) -> bool: ...
    async def fetch_signals(self, since: datetime | None = None,
                            cursor: str | None = None) -> AsyncIterator[RawSignal]: ...

# signal-normalizer/model.py
class NormalizedSignal(BaseModel):
    signal_id: str
    exchange: str
    source: str
    trader_id: str
    symbol: str
    market: Literal["spot","swap","future"]
    side: Literal["open_long","open_short","close_long","close_short"]
    leverage: float
    qty: float
    entry_price: float | None
    sl: float | None
    tp: list[float]
    opened_at: datetime

# risk-engine/engine.py
class RiskEngine:
    async def evaluate(self, user_id: int,
                       signal: NormalizedSignal,
                       intent: OrderIntent) -> RiskDecision: ...

# executor/order_router.py
class OrderRouter:
    async def place(self, intent: OrderIntent,
                    user_ctx: UserContext) -> ExecutionReport: ...
```

---

## 11. 当前状态分析与变更清单

### Current State Analysis

- 工作区已存在大量历史项目（PA 量化、Gate.io 跟单、网格系统等），不直接复用。
- 没有现成的"多交易所信号聚合"框架代码，需要从零创建。
- 本次任务范围：**只输出开发框架文档**，不落任何实现代码。

### Proposed Changes（仅规划，不执行）

| 文件 | 目的 | 关键内容 |
|---|---|---|
| `.trae/documents/2026-08-11-signal-aggregator-platform-framework.md` | 框架规划文档 | 本文档全部内容 |

后续如需落地，依次创建：

| 目录/文件 | 目的 |
|---|---|
| `signal-aggregator/` | 新项目根目录 |
| `signal-aggregator/pyproject.toml` | Python 项目元数据 + 依赖 |
| `signal-aggregator/.env.example` | 环境变量示例 |
| `signal-aggregator/docker-compose.yml` | 本地一键起 |
| `signal-aggregator/Makefile` | 启动/迁移/测试快捷命令 |
| `signal-aggregator/exchange-adapters/base/*.py` | 适配器 ABC |
| `signal-aggregator/{signal-collector,signal-normalizer,signal-store,risk-engine,executor,trade-tracker,notification,web-api,web-ui,config,observability,tests}/...` | 13 个模块骨架 |

### Assumptions & Decisions

- **A1**：5 家交易所均采用统一的 `AbstractExchangeAdapter` 接口，三种采集策略用三个 ABC 分层。
- **A2**：用 Redis Streams（而非 Kafka）作为事件总线；理由：单机起步成本低，Python 生态成熟；后续可替换为 Kafka/NATS。
- **A3**：用户 API key 采用 AES-256-GCM 加密，主密钥经环境变量注入；KMS 留 ABC 接口。
- **A4**：前端使用 Next.js 14 App Router + shadcn/ui + ECharts；WS 推送信号流。
- **A5**：数据库使用 PG（业务）+ TimescaleDB（时序）+ Redis（缓存/总线）。
- **A6**：风控只给框架不写规则阈值（用户要求"只做框架"）。
- **A7**：依赖 Pydantic v2、SQLAlchemy 2.x async、ccxt>=4.5、httpx>=0.27、websockets>=12、cryptography>=42。

### Verification

- 框架文档可读性：文档结构完整（10+ 章节）、接口签名可被下游 agent 直接实现。
- 接口契约一致性：13 个模块的输入输出通过 Redis Streams topic 全部对得上。
- 与 gate_copy_trading 边界清晰：第 7 章给出 10 个维度的差异表，避免后续混淆。
- 数据安全约束明确：第 2.6 节列出加密方案；第 12 节给出实现 agent 的硬约束。

---

## 12. 给后续实现 Agent 的边界提示

- 本文档**不包含**任何可直接运行的生产代码；只定义类型/接口/目录。
- 任何模块的实现 agent 必须：
  1. 先读取本文件中对应小节；
  2. 按接口签名生成 Pydantic 模型和 ABC；
  3. 在每个函数体内只写 `TODO: ...` 与最小可用 `raise NotImplementedError`；
  4. 不在本阶段实现加密细则、风控细则、限流具体值；
  5. 不要修改其他模块的接口；如发现契约缺口，回写到本文件再实现。
- **数据安全硬约束**：任何落盘的 API key/secret 必须经过 `executor/vault.py` 的 `ApiKeyVault.encrypt()`；禁止明文出现在日志、ORM 模型字段、错误信息中。

---

文档结束。