# 五 CEX 信号聚合跟单 SaaS 平台 — 产品与技术设计文档

> 路径：`c:\Users\w6485\Desktop\AI 量化\.trae\documents\2026-08-12-signal-saas-platform-design.md`
> 文档定位：基于已上传的完整需求文档(10 章节)整理出的产品+技术一体化设计蓝本；不含可运行实现。
> 关联文档：`.trae/documents/2026-08-11-signal-aggregator-platform-framework.md`(V2 多所抽象层)、`gate-copy-trading-completion-plan.md`(既有 Gate 单所参考)

---

## 1. 项目概述与目标

### 1.1 产品定位

- **项目名称**：五大主流 CEX 信号聚合跟单 SaaS 平台(代号 `signal-saas`)。
- **目标市场**：Binance / OKX / Bybit / Bitget / Gate.io 5 大合约交易所。
- **本质角色**：**信号聚合者 + 跟单工具提供商**——平台本身**不生产信号**,**不做自营信号**,只抓取 5 大交易所带单广场公开数据,对外以"策略广场"包装,对内以"独立跟单机器人"执行。
- **目标用户**：资金体量不大的中小散户,无专业盯盘时间,希望"抄作业"的普通合约用户(★ G24 补充 §1.4 用户画像)。
- **资金流向**：用户资金 100% 在用户本人交易所账户内;平台仅持有用户授权的"读取 + 合约交易" API 权限;**绝对禁止**绑定任何带有"提现/转账"权限的 API。
- **合规边界**：**不碰 5% 交易返佣**,**不抽水、不分润**,唯一收入为订阅费(5U 试用 / 19.9U 正式 / 主号下级免费)。所有收益由用户交易盈亏自行承担,平台仅承担工具责任。

### 1.2 业务目标

1. V1 在 Gate.io 单交易所实现"采集 → 标准化 → 包装 → 跟单 → 结算 → 提现"完整闭环。
2. V1.1 / V1.2 横向扩展到 OKX / Bybit / Bitget / Binance,架构预留 5 家 × 双轨采集。
3. V2 引入"模式 B 小号 WS"以降低延迟,同时引入多链提现与地址白名单。
4. 后台覆盖用户/审核/信号/订单/支付/邀请/钱包/提现/风控/日志 10 模块,前台覆盖首页/策略广场/我的跟单/个人中心/邀请/奖励/提现 7 大场景。

### 1.3 非目标

- 不生产自营信号、不做"机构带单"、不挂单做市、不提供投顾建议。
- 不接入法币入金、不开发手机号注册、不开放第三方 OAuth 登录(V1)。
- 不直接管理用户资金、不碰交易所"提现"权限、不替用户托管 USDT。
- 不承诺保本、不承诺收益、不代客理财;强制风险揭示模态框。

### 1.4 用户画像（★ G24）

- **典型用户**：资金 200-5,000 USDT 的中小散户，无专业盯盘时间，依赖"抄作业"式跟单。
- **行为特征**：白天工作、晚间查看收益；偏好一键开启跟单、低学习成本；对延迟不敏感（秒级可接受）。
- **决策动机**：跟单人数多 / 收益曲线稳定 / 风险评级低 → 更容易转化订阅。
- **画像落地**：首页新手引导（G23）、金额隐私小眼睛（G22）、策略卡片风险评级标签均据此设计。

### 1.5 需求修复编号索引（★ Gxx）

> 需求修复项以 `★Gxx` 编号跟踪，编号从 **G03** 起连续递增，**G01/G02 未启用、G14-G20 保留空号**（供后续需求修复使用）。已定义编号：G03（动作路由）、G04（带单门槛）、G05（画像扩展）、G06（平台池）、G07（保证金模式）、G08（合约规格）、G09（三链校验）、G10（订阅过期拦截）、G11（邀请风控 48h）、G12（5 字段账本）、G13（提现门槛）、G21-G27（前端/后台需求细化）。全部编号在设计文档正文有正式定义，且开发计划均有落地任务。

---

## 2. 系统架构图(文字版)

### 2.1 总体分层

> ★ 单体化（2026-08-12）：后端为**单个 FastAPI 应用**，19 个业务模块（§3.3-3.21）+ 2 个前端应用（web-ui/web-admin）共 21 个模块；后端模块收敛为 `api/` 内包，通过依赖注入组装，不做微服务/网关/独立服务进程（Celery worker 属单体内的进程内任务队列，见框架文档 §3）。工程骨架见 `2026-08-12-signal-saas-project-framework.md`。

```
┌─────────────────────────────────────────────────────────────────────┐
│                        客户端层 (Client)                              │
│  ┌────────────────────┐                       ┌──────────────────┐ │
│  │ Web 用户前台 web-ui│                       │ Web 后台 web-admin│ │
│  │ (Next.js 14)       │                       │ (Next.js 14)     │ │
│  └─────────┬──────────┘                       └────────┬─────────┘ │
└────────────┼────────────────────────────────────────┼──────────────┘
             │ HTTPS REST + WSS                       │ HTTPS REST
             ▼                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI 单体应用 (api，唯一后端)                   │
│   main.py + deps.py ── 路由注册 / 鉴权 / 限流 / 依赖注入              │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  routers/  (auth/identity/apikeys/strategies/bots/... admin)  │  │
│  └───────────────────────────────┬───────────────────────────────┘  │
│                                   ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  services/  21 个业务模块（核心逻辑，函数调用+依赖注入）      │    │
│  │  auth identity billing payment withdrawal referral ledger    │    │
│  │  apikeyvault scraper normalizer signalstore copyengine       │    │
│  │  riskengine executor tradetracker audit mailer notification  │    │
│  │  observability                                              │    │
│  └───────────────┬──────────────────────────┬──────────────────┘    │
│                  ▼                          ▼                       │
│         ┌────────────────┐        ┌─────────────────────┐           │
│         │ workers/       │        │ ws/                 │           │
│         │ Celery 任务    │        │ WebSocket Hub       │           │
│         │ 爬虫/画像/支付  │        │ 6 频道实时推送       │           │
│         └────────┬───────┘        └──────────┬──────────┘           │
└──────────────────┼──────────────────────────┼────────────────────────┘
                   ▼                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    数据 & 基础设施层                                   │
│  PostgreSQL(业务单库)   Redis(缓存/队列/Celery/Pub-Sub)               │
│  PostgreSQL 分区表承载画像/订单时序（V1 不引入独立时序库）              │
└─────────────────────────────────────────────────────────────────────┘
        │                       │                              │
        ▼                       ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       外部连接层                                       │
│  5×CEX 官方 API (直连)  区块链 RPC (TronGrid/BSCScan/Etherscan)      │
│  邮件 SMTP          站内消息(WS 推送)                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块边界契约

| 起点 | 终点 | 契约 | 通道 |
|---|---|---|---|
| adapters → normalizer | `RawSignal` | REST + Redis Stream | `signal.raw.received.v1` |
| normalizer → signal-store | `NormalizedSignal` | SQL + Stream | `signal.normalized.v1` |
| signal-store → copy-engine | `SignalSnapshot` | DB 读 + Pub/Sub | Redis |
| copy-engine → risk-engine | `OrderIntent` | 同步调用 | 函数调用（单体应用内） |
| risk-engine → executor | `ApprovedIntent` | 异步队列 | Celery + Redis |
| executor → trade-tracker | `ExecutionReport` | Stream | `order.placed.v1` |
| web-api → web-ui | `JSON` / WSS frame | HTTPS / WSS | `/v1/*` + `/ws/stream` |
| payment-svc → mailer | `EmailTask` | Celery | SMTP |
| withdrawal-svc | `WithdrawalRequest` | REST | `/v1/withdrawals` |
| admin/web-admin → audit-log | `AuditEvent` | 同步写 | PG |

---

## 3. 模块划分(后端 19 个业务模块 + 前端 2 个应用)

> 命名约定：服务级以 `-svc` 结尾,引擎级以 `-engine` 结尾。所有模块只暴露接口签名,不暴露实现。

### 3.1 前台 web-ui(Next.js 14 App Router)

- **职责**：用户 SPA;策略广场、跟单配置、邀请/奖励/提现交互、首页数据看板。
- **文件骨架**：
  ```
  web-ui/app/
  ├── (marketing)/page.tsx
  ├── (auth)/{login,register}/page.tsx
  ├── strategies/{page,[id]/page}.tsx
  ├── bots/page.tsx
  ├── account/{page,apikeys/page}.tsx
  ├── invite/page.tsx
  ├── rewards/page.tsx
  ├── withdraw/page.tsx
  └── layout.tsx
  web-ui/components/{StrategyCard,BotCard,RewardTable,WithdrawalForm,ApiKeyForm,AddressInput}.tsx
  web-ui/lib/{api.ts,ws.ts}
  web-ui/stores/{useAuth,useBots,useRewards}.ts
  ```

### 3.2 后台 web-admin(Next.js 14)

- **职责**：管理员入口;10 大模块对应页面 + RBAC。
- **文件骨架**：
  ```
  web-admin/app/
  ├── login/page.tsx
  ├── dashboard/page.tsx
  ├── users/{page,detail/[id]}.tsx
  ├── review/page.tsx
  ├── signals/{page,[exchange]/page,detail/[id]}.tsx
  ├── orders/page.tsx
  ├── payments/page.tsx
  ├── invites/page.tsx
  ├── wallets/page.tsx
  ├── withdrawals/page.tsx
  ├── risk/page.tsx
  └── audit/page.tsx
  ```
- **关键约束**：与用户前台**完全隔离**的登录入口、cookie 域、JWT audience;写接口强制 audit-log。

### 3.3 后端 api(FastAPI)

- **职责**：唯一对外 HTTP/WSS 入口;组装所有 svc,提供 OpenAPI、鉴权、限流、WS Hub。
- **文件骨架**：
  ```
  api/
  ├── main.py
  ├── deps.py
  ├── middlewares/{auth,ratelimit,cors,request_id}.py
  ├── routers/
  │   ├── auth.py        # /v1/auth/*
  │   ├── identity.py    # /v1/identity
  │   ├── apikeys.py     # /v1/apikeys
  │   ├── strategies.py
  │   ├── bots.py
  │   ├── subscriptions.py
  │   ├── payments.py
  │   ├── referrals.py
  │   ├── rewards.py
  │   ├── withdrawals.py
  │   ├── ws.py          # /ws/stream
  │   └── admin/{users,review,signals,orders,payments,invites,exchange_invites,wallets,withdrawals,risk,audit}.py
  ├── schemas/
  ├── workers/            # Celery 任务（进程内队列，见框架文档 §3）
  │   ├── scraper_tasks.py    # 定时采集
  │   ├── copy_tasks.py       # 跟单执行
  │   └── payment_tasks.py    # 链上轮询
  └── errors.py
  ```

### 3.4 账户/认证 auth-svc

```python
class AuthService:
    async def register(email: EmailStr, password: SecretStr) -> User: ...
    async def verify_email(email: EmailStr, code: str) -> None: ...
    async def login(email: EmailStr, password: SecretStr, mfa: str | None) -> TokenPair: ...
    async def logout(jti: str) -> None: ...
    async def change_password(user_id: int, old: SecretStr, new: SecretStr) -> None: ...
    async def send_reset(email: EmailStr) -> None: ...
    async def reset_password(token: str, new: SecretStr) -> None: ...
```

### 3.5 身份与邀请码 identity-svc

> **G06 修复**：新增 `PlatformPool` 表与自动识别逻辑。用户绑定邀请码时，系统自动检查该码是否命中平台资源池，若命中且用户所选交易所匹配，则自动标记为主号下级（免订阅）。

```python
class IdentityService:
    async def choose_exchange(user_id: int, exchange: Exchange) -> Identity: ...
    async def bind_invite_code(user_id: int, code: str) -> Invite: ...
    async def validate_no_cycle(user_id: int, ancestor_id: int) -> bool: ...
    async def mark_as_sub_account(user_id: int, admin_id: int) -> None: ...
    async def auto_detect_platform_pool(self, user_id: int, invite_code: str) -> bool: ...
        # 1. 查 platform_pool 表：invite_code 匹配且 is_active=true
        # 2. 检查 identity.exchange == pool.exchange
        # 3. 匹配成功 → identity_type='sub_account'，写 audit-log
        # 4. 匹配失败 → 保持 normal，不触发任何奖励流程
```

**PlatformPool 数据模型**：

| 表 | 关键字段 | 关键约束 |
|---|---|---|
| PlatformPool | invite_code(UNIQUE), exchange, label, is_active, created_at | 平台资源池专属邀请码，绑定合作交易所 |

> **★ G27 修复（2026-08-12）— 交易所邀请码管理**：新增 `ExchangeInviteCode` 表，管理**平台作为交易所合作方持有的邀请码**（每所可多个）。用户选所后必须填写对应交易所邀请码，后端核实有效性后绑定（用于合作返佣归属/注册归属核实）。与"用户好友邀请码"（Identity.invite_code）和"平台池码"（PlatformPool 主号下级免订阅）是三个独立概念。

```python
class ExchangeInviteCode(BaseModel):
    id: int
    exchange: Exchange          # gate/binance/okx/bybit/bitget
    code: str                   # 交易所侧邀请码（如 gate 的 8F3K2A）
    status: Literal['active','inactive']   # 启用/停用
    remark: str | None          # 用途备注（渠道/批次）
    bind_count: int = 0         # 已绑定用户数
    max_binds: int | None       # 绑定上限（None=不限）
    created_at: datetime

class ExchangeInviteService:
    async def list_codes(self, exchange: Exchange | None) -> list[ExchangeInviteCode]: ...
    async def create_code(self, exchange: Exchange, code: str, remark: str) -> ExchangeInviteCode: ...
    async def set_status(self, code_id: int, status: str, admin_id: int) -> None: ...
        # 停用/启用均写 audit-log
    async def verify_and_bind(self, user_id: int, exchange: Exchange, code: str) -> tuple[bool, str]:
        # ★ G27 核实逻辑
        # 1. code 在 exchange_invite_codes 中存在且 status='active'
        # 2. 达到 max_binds 上限 → 拒绝（提示换码）
        # 3. 绑定成功 → Identity.exchange_invite_code=code, bind_count+=1, 写 audit-log
        # 4. 失败 → 返回具体原因（码不存在/已停用/已达上限/非本所码）
```

**注册流程（G27 接入 §6.1）**：选所（choose-exchange）→ **填写对应交易所邀请码**（verify_and_bind，强制必填）→ 好友邀请码（可选）→ 完成。交易所邀请码与好友邀请码互不冲突，可同时绑定。

**后台管理（§7.3 新增）**：`GET/POST /admin/v1/exchange-invites`（列表/新增）、`PATCH /admin/v1/exchange-invites/{id}`（启停用），每个交易所多个码独立维护。

### 3.6 订阅计费 billing-svc

```python
class BillingService:
    async def list_plans() -> list[Plan]: ...
    async def start_subscription(user_id: int, plan_id: str) -> PaymentOrder: ...
    async def activate_after_payment(order_id: int) -> Subscription: ...
    async def get_active_subscription(user_id: int) -> Subscription | None: ...
    async def assert_can_follow(user_id: int) -> None: ...
    async def expire_due_subscriptions() -> int: ...
```

### 3.7 支付核对 payment-svc

> **★ G09 修复（2026-08-12）— 三链即时校验**：链上支付自动校验支持 TRC-20 / BEP-20 / ERC-20 三条链（web3.py + tronpy）。instant_verify 四连校验（network/to_address/value/tx.status），poll 阈值 12/15/12 确认，连续 3 次 API 错误或 4 轮不足转 manual/timeout（见 §6.5）。

```python
class PaymentService:
    async def create_order(user_id: int, plan_id: str, network: Network) -> PaymentOrder: ...
    async def submit_txhash(order_id: int, tx_hash: str, network: Network) -> PaymentOrder: ...
    async def instant_verify(order: PaymentOrder) -> bool: ...
    async def poll_confirmations(order: PaymentOrder) -> None: ...
    async def finalize(order: PaymentOrder) -> PaymentOrder: ...
    async def mark_timeout(order: PaymentOrder) -> None: ...
    async def manual_confirm(order_id: int, admin_id: int) -> None: ...
```

### 3.8 提现审核 withdrawal-svc

```python
class WithdrawalService:
    async def create(user_id: int, amount: Decimal, network: Network, address: str) -> Withdrawal: ...
    async def approve(withdrawal_id: int, admin_id: int) -> Withdrawal: ...
    async def reject(withdrawal_id: int, admin_id: int, reason: str) -> Withdrawal: ...
    async def fill_txhash(withdrawal_id: int, admin_id: int, tx_hash: str) -> Withdrawal: ...
    async def verify_onchain(withdrawal: Withdrawal) -> bool: ...
    async def retry(withdrawal_id: int, admin_id: int) -> Withdrawal: ...
    async def refund(withdrawal_id: int, admin_id: int) -> Withdrawal: ...
```

### 3.9 邀请与奖励 referral-svc

```python
class ReferralService:
    async def generate_code(owner_id: int) -> str: ...
    async def resolve(code: str) -> User: ...
    async def list_invites(owner_id: int) -> list[Invite]: ...
    async def should_trigger_reward(order: PaymentOrder) -> bool: ...
    async def detect_batch_abuse(owner_id: int, window: timedelta) -> RiskFlag: ...
```

### 3.10 奖励账本 ledger-svc(流水账)

```python
class BalanceSnapshot(BaseModel):
    """★ G12 修复：5 个字段完整定义"""
    total_earned: Decimal          # 累计奖励（所有记录 SUM，含已取消/已回滚）
    available: Decimal             # 可提现余额（status='available' 的 SUM）
    withdrawing: Decimal           # 提现中金额（status='withdrawing' 的 SUM）
    paid: Decimal                  # 已提现金额（status='paid' 的 SUM）
    frozen: Decimal                # ★ G12 新增：冻结金额（status='frozen' 的 SUM）
    # 校验不变量：total_earned = available + withdrawing + paid + frozen + canceled + rolled_back

class LedgerService:
    async def credit(user_id: int, source: RewardSource, amount: Decimal, ref_id: int) -> Reward: ...
        # ★ G11 修复：根据风控标记动态设置核实期
        # risk_flag = await referral.detect_batch_abuse(user_id, window=1h)
        # if risk_flag.is_flagged → verifying_ends_at = now + 48h
        # else → verifying_ends_at = now + 24h
    async def freeze(user_id: int, reward_id: int) -> Reward: ...
    async def release(user_id: int, reward_id: int) -> Reward: ...
    async def rollback(user_id: int, ref_id: int, reason: str) -> Reward: ...
    async def get_balance(user_id: int) -> BalanceSnapshot: ...
        # ★ G12 修复：返回 5 字段 BalanceSnapshot（含 frozen）
```

### 3.11 交易所 API 凭证 api-vault(AES 加密)

```python
class ApiKeyVault:
    def __init__(self, master_key: bytes, kms: KmsClient | None = None): ...
    def encrypt(self, plaintext: bytes, aad: bytes) -> bytes: ...      # nonce(12) + ct + tag(16)
    def decrypt(self, ciphertext: bytes, aad: bytes) -> bytes: ...
    async def store(user_id: int, exchange: Exchange, key: str, secret: str) -> ApiKey: ...
    async def fetch_credential(user_id: int, exchange: Exchange) -> tuple[str, str]: ...
    async def rotate_master_key(self) -> None: ...
```

- **加密方案**：AES-256-GCM;nonce 12B;tag 16B;AAD 绑定 `user_id|exchange|key_id`;主密钥经 `MASTER_KEY_B64` 注入或 KMS。

### 3.12 信号采集 adapters(5 家 × 爬虫优先)

```python
class AbstractScraperAdapter(ABC):
    exchange: Exchange
    async def health(self) -> bool: ...
    async def fetch_public_positions(self, since: datetime | None = None) -> AsyncIterator[RawPosition]: ...
    async def fetch_trader_profile(self, trader_id: str) -> TraderProfile: ...
    async def fetch_top_traders(self, period: str, limit: int) -> list[TraderSummary]: ...
```

### 3.13 信号标准化 normalizer

```python
class SignalAction(str, Enum):
    OPEN   = "open"    # 开仓
    ADD    = "add"     # 加仓
    REDUCE = "reduce"  # 减仓
    CLOSE  = "close"   # 平仓

class NormalizedSignal(BaseModel):
    exchange: Exchange
    source_trader_id: str
    symbol: str                 # 平台标准代码（如 ETHUSDT）
    side: Literal['long', 'short']
    action: SignalAction         # ★ 新增：动作类型（开/加/减/平）
    qty: Decimal
    leverage: int
    price: Decimal | None        # 信号源开仓价（如有）
    prev_qty: Decimal | None     # ★ 新增：上一次持仓量（用于判断 add/reduce 幅度）
    received_at: datetime
    source_mode: Literal['A', 'B']
    contract: 'ContractSpec'     # ★ 新增：关联合约规格（G08）

class NoiseFilterConfig(BaseModel):
    min_position_change_pct: Decimal = Decimal("0.05")   # 调仓幅度 <5% 视为噪声
    min_holding_seconds: int = 30                         # 持仓 <30s 视为试单
    dedupe_window_seconds: int = 5                         # 同一交易员同币种 5s 内去重

class SignalNormalizer:
    def __init__(self, noise_cfg: NoiseFilterConfig): ...
    async def normalize(self, raw: RawSignal) -> NormalizedSignal: ...
    async def dedupe_key(self, ns: NormalizedSignal) -> str: ...   # exchange|trader|symbol|side|action|opened_at
    async def filter_noise(self, ns: NormalizedSignal, prev: NormalizedSignal | None) -> bool: ...
        # 过滤逻辑：
        # 1. 调仓幅度 < min_position_change_pct → 丢弃
        # 2. 同一交易员同币种 5s 内重复 → 丢弃
        # 3. 开仓后 30s 内平仓 → 视为试单丢弃
```

### 3.14 信号存储与画像 signal-store

```python
class TraderSelectionPolicy:
    """★ G04 修复：带单员选取硬性门槛（V1 默认值，后台可配置）"""
    MIN_WIN_RATE = Decimal("55")        # 历史胜率 ≥ 55%
    MAX_DRAWDOWN = Decimal("30")        # 最大回撤 ≤ 30%
    MIN_TRADING_DAYS = 30              # 带单天数 ≥ 30

class SignalStore:
    async def upsert_trader(self, t: Trader) -> Trader: ...
    async def upsert_strategy(self, s: Strategy) -> Strategy: ...
    async def insert_signal(self, s: NormalizedSignal) -> SourceSignal: ...
    async def sync_daily_profiles(self, exchange: Exchange) -> int: ...
    async def get_strategy_with_profile(self, strategy_id: int) -> tuple[Strategy, TraderProfile]: ...
    async def add_to_listed(self, exchange: str, trader_id: str, admin_id: int,
                            display_name: str, style: str, risk_rating: str,
                            force: bool = False, force_reason: str | None = None) -> Strategy: ...
        # ★ G04 修复：上架前校验门槛
        # 1. 获取最新 TraderProfile
        # 2. 检查 win_rate_all >= 55% AND max_drawdown <= 30% AND trading_days >= 30
        # 3. 不满足 → 拒绝；force=True 时跳过但必须填 force_reason + 写 audit-log
        # 4. 满足 → 写入 Strategy 表（status=listed）
```

### 3.15 跟单引擎 copy-engine(核心)

```python
class BotConfig(BaseModel):
    amount_mode: Literal['fixed', 'percent']
    fixed_amount_usdt: Decimal | None       # amount_mode=fixed 时必填
    percent: int | None                     # amount_mode=percent 时必填 (1-100)
    leverage: int
    margin_mode: Literal['isolated', 'cross']   # ★ G07 新增：逐仓/全仓
    max_total_position_usdt: Decimal

class CopyEngine:
    async def create_bot(self, user_id: int, strategy_id: int, cfg: BotConfig) -> CopyBot: ...
    async def update_bot(self, bot_id: int, cfg: BotConfig) -> CopyBot: ...
    async def pause(self, bot_id: int) -> CopyBot: ...
    async def resume(self, bot_id: int) -> CopyBot: ...
    async def on_signal(self, ns: NormalizedSignal) -> list[OrderIntent]: ...
        # ★ G03 修复：按 action 类型路由
        # OPEN  → 新建仓位，走完整 USDT 4 步换算
        # ADD   → 加仓，检查是否超过 max_total_position
        # REDUCE → 按比例减仓
        # CLOSE  → 全部平仓
        # ★ G10 预留：订阅过期时拦截 OPEN/ADD，放行 REDUCE/CLOSE
    async def compute_size(self, bot: CopyBot, ns: NormalizedSignal) -> tuple[Decimal, Decimal]: ...
        # ★ G08 修复：合约规格从 ns.contract 获取（合约级别），不再从交易所级别获取
    async def virtual_ledger_lock(self, bot_id: int, amount: Decimal) -> None: ...
    async def virtual_ledger_release(self, bot_id: int, amount: Decimal) -> None: ...
```

### 3.16 风控引擎 risk-engine

```python
class RiskEngine:
    async def evaluate(self, user_id: int, bot: CopyBot, intent: OrderIntent, signal: NormalizedSignal) -> RiskDecision: ...
    async def global_throttle(self, exchange: Exchange) -> bool: ...
    async def delay_redline(self, signal_age_ms: int, mode: Literal['A','B']) -> bool: ...
    async def emergency_stop_all(self, reason: str) -> None: ...
    async def detect_invite_fraud(self, owner_id: int) -> RiskFlag: ...
```

### 3.17 订单执行器 executor(官方直连 + 滑点保护)

> ★ 决策 B（2026-08-12）：弃用 ccxt，直接对接 5 家交易所官方 API。`OrderRouter` 通过统一 `ExchangeAdapter` 抽象调用官方客户端（见框架文档 §3 `exchange_clients/`），签名/限流/WS 重连自研。

```python
class OrderRouter:
    def __init__(self, adapter: ExchangeAdapter): ...   # 按 exchange 注入官方客户端
    async def place(self, intent: OrderIntent, user_ctx: UserContext) -> ExecutionReport: ...
    async def cancel(self, order_id: str, user_ctx: UserContext) -> bool: ...
    async def set_leverage(self, symbol: str, leverage: int, user_ctx: UserContext) -> None: ...
    async def set_margin_mode(self, symbol: str, mode: Literal['isolated','cross'], user_ctx: UserContext) -> None: ...
```

### 3.18 成交跟踪 trade-tracker

```python
class TradeTracker:
    async def attach_user(self, user_id: int, exchange: Exchange) -> None: ...
    async def detach_user(self, user_id: int, exchange: Exchange) -> None: ...
    async def reconcile_position(self, user_id: int, exchange: Exchange, symbol: str) -> PositionSnapshot: ...
    async def realized_pnl_today(self, user_id: int) -> Decimal: ...
    async def unrealized_pnl(self, user_id: int) -> Decimal: ...
```

### 3.19 后台操作审计 audit-log

```python
class AuditService:
    async def record(self, actor: Actor, action: str, target: str, before: dict, after: dict, reason: str | None) -> AuditEvent: ...
    async def list_events(self, filter: AuditFilter) -> list[AuditEvent]: ...
    async def export(self, range_: tuple[datetime, datetime]) -> bytes: ...
```

### 3.20 邮件通知 + 站内消息 mailer + notification

> 需求要求的通信方式：邮箱（注册验证码 / 支付超时 / 提现成功）+ 站内消息（WS 实时推送）。不包含微信、Telegram、短信等第三方即时通讯服务。

```python
class Mailer:
    """邮件服务（SMTP）— 用于注册验证码、支付通知、提现通知"""
    async def send(self, to: EmailStr, template: str, context: dict) -> None: ...
    async def send_bulk(self, recipients: list[EmailStr], template: str, context: dict) -> None: ...
    async def render(self, template: str, context: dict) -> MimeMessage: ...

class NotificationService:
    """站内消息服务 — 通过 WebSocket 实时推送到前端"""
    async def push(self, user_id: int, type: str, title: str, body: dict) -> None: ...
        # 通过 /ws/stream 推送给在线用户
        # 离线用户在下次连接时拉取未读消息
    async def mark_read(self, user_id: int, notification_id: int) -> None: ...
    async def list_unread(self, user_id: int) -> list[Notification]: ...
```

**通知触发场景**（与需求一一对应）：

| 场景 | 通道 | 需求出处 |
|------|------|---------|
| 注册验证码 | 邮件 | §3.1 |
| 支付确认超时 | 邮件 + 站内消息 | §5.4④ |
| 订阅开通成功 | 站内消息 | §5.4③ |
| 奖励核实完成 | 站内消息 | §6.3 |
| 提现审核通过/拒绝 | 邮件 + 站内消息 | §8.3 |
| 风控冻结通知 | 站内消息 | §8.4 |

### 3.21 监控告警 observability

```python
def setup_logging(service: str) -> None: ...
def metrics_counter(name: str, labels: dict[str, str]) -> Counter: ...
def trace_span(name: str) -> ContextManager: ...
def readiness_check(deps: list[Dep]) -> Callable: ...
```

---

## 4. 关键数据模型

### 4.1 ER 总览

```
User 1—1 Identity 1—1 IdentityExchange
User 1—N ApiKey
User 1—1 Invite (inviter_id → User)
User 1—N Subscription 1—1 PaymentOrder
User 1—N CopyBot N—1 Strategy
CopyBot 1—N CopyOrder N—1 NormalizedSignal
Strategy 1—1 Trader N—1 Exchange
Trader 1—N TraderProfile (按日)
User 1—N Reward
User 1—N Withdrawal
PlatformPool (独立表, G06)              ← 平台资源池邀请码
ExchangeInviteCode (独立表, G27)        ← 交易所邀请码（每所多码，UNIQUE(exchange,code)）
ContractSpec N—1 Exchange (独立表, G08)  ← 合约级精度参数
NormalizedSignal 1—1 ContractSpec (G08)  ← 信号关联合约规格
```

### 4.2 核心字段(精简呈现)

| 表 | 关键字段 | 关键约束 |
|---|---|---|
| User | id, email(CITEXT UNIQUE), password_hash, is_active, is_frozen, role | |
| Identity | user_id PK, exchange, invite_code, exchange_invite_code, inviter_id, identity_type(normal/sub_account), locked | UNIQUE(exchange,user_id)；★ G27 新增 exchange_invite_code |
| ApiKey | user_id, exchange, ciphertext, nonce, tag, aad, status | UNIQUE(user_id, exchange) |
| SourceSignal | exchange, source_trader_id, symbol, side, leverage, qty, action(open/add/reduce/close), opened_at, dedupe_key | UNIQUE(dedupe_key)；★ G03 action 字段 |
| Trader | exchange, trader_id | UNIQUE(exchange, trader_id) |
| Strategy | trader_id, source_exchange, display_name, style, risk_rating, status | |
| TraderProfile | trader_id, snapshot_date, roi_7d, roi_30d, roi_90d, roi_all, win_rate_30d, win_rate_all, max_drawdown, trading_days | ★ G05 扩展：roi_90d, roi_all, win_rate_all, trading_days; UNIQUE(trader_id, snapshot_date) |
| Subscription | user_id, plan_id(trial_5u/monthly_19_9u), status, expires_at, payment_order_id | 试用唯一性 |
| PaymentOrder | user_id, plan_id, amount_usdt, network(TRC20/BEP20/ERC20), tx_hash, status, confirmations, required_confirmations(12/15/12), poll_attempts(≤6) | ★ G09 新增：三链即时校验 |
| CopyBot | user_id, strategy_id, exchange, api_key_id, amount_mode(fixed/percent), fixed_amount_usdt, percent, leverage, margin_mode(isolated/cross), max_total_position_usdt, virtual_locked_usdt, status | ★ G07 新增 margin_mode |
| ContractSpec | exchange, symbol, face_value_usdt, min_size, size_precision, contract_type(USDT-margined) | ★ G08 新增：合约级精度参数; UNIQUE(exchange, symbol) |
| PlatformPool | invite_code(UNIQUE), exchange, label, is_active | ★ G06 新增：平台资源池 |
| ExchangeInviteCode | exchange, code, status(active/inactive), remark, bind_count, max_binds | ★ G27 新增：交易所邀请码（每所多码）；UNIQUE(exchange, code) |
| CopyOrder | bot_id, signal_id, action(open/add/reduce/close), qty, leverage, required_margin_usdt, status, failure_category, latency_ms | ★ G03 新增 action; failure_category: balance/permission/leverage/symbol/min_size/network/price_deviation/slippage/other |
| Invite | inviter_id, invitee_id, code, bound_at, locked | UNIQUE(invitee_id) |
| Reward | owner_id, source_user_id, source_payment_order_id, amount_usdt, status(verifying/available/withdrawing/paid/frozen/canceled/paid_failed/rolled_back), verifying_started_at, verifying_ends_at | |
| Withdrawal | user_id, amount_request, fee_usdt(1.00), network(TRC20/BEP20), to_address, status, admin_reviewer_id, tx_hash, tx_verified | |

---

## 5. 关键状态机

### 5.1 订阅状态机

```
[none] ─购买─▶ [pending] ─提交TxHash─▶ [verifying] ─阈值达标─▶ [active]
                                                          │
                                                          └─超时/失败─▶ [timeout/failed] ─管理员手动─▶ [active]
[active] ─到期─▶ [expired]
[active] ─风控─▶ [frozen]
[expired] ─续费─▶ [pending]
主号下级身份自动 = [active]
```

### 5.2 支付订单状态机

```
[pending] ─submitTxHash─▶ [verifying] ─即时校验通过─▶ [polling]
   │                                  │
   └─即时校验失败─▶ [failed]          ├─confirmations ≥阈值─▶ [confirmed] ─▶ billing.activate
                                       ├─4 轮轮询仍不足─▶ [timeout] ─▶邮件+异常池
                                       ├─API 连续 3 次网络错─▶ [manual]
                                       └─poll_attempts ≥ 6 ─▶ [manual]
[manual] ─管理员"强制确认开通"─▶ [confirmed]
任一态 ─管理员"作废"─▶ [failed]
```

### 5.3 奖励状态机

```
[verifying] ─24h 倒计时无异常─▶ [available]
   │
   └─24h 内下级退款/回滚─▶ [canceled]
[available] ─申请提现─▶ [withdrawing]
   ├─审核通过 + TxHash 验证通过─▶ [paid]
   ├─审核通过但链上失败─▶ [paid_failed]
   └─审核拒绝─▶ [available](退回)
[paid] ─下级事后恶意退款─▶ [rolled_back]
任意态 ─风控冻结─▶ [frozen]
```

### 5.4 提现状态机

```
前置：可提现余额 ≥ 10U（★ G13 统一：以 §5.4 专章 10U 为准） + 1U 手续费
提交申请 ─▶ [available_locked](资金从"可提现"扣至"提现中")
   ▼
[pending_review] ─管理员审核─▶ [approved]
   ├─管理员转账成功 + 填 TxHash + 链上校验通过─▶ [paid]
   ├─管理员转账失败─▶ [paid_failed] ─重试─▶ [approved]
   ├─管理员拒绝─▶ [rejected]
   └─管理员"退还申请"─▶ [refunded] ─▶ 资金回退至"可提现"
```

### 5.5 CopyBot 状态机

```
[created] ─开启─▶ [active]
[active] ─暂停─▶ [paused]
[paused] ─恢复─▶ [active]
[active/paused] ─风控制动─▶ [errored]
[errored] ─管理员解除─▶ [active/paused]
任一态 ─订阅过期/冻结─▶ ★ G10 修复：信号路由层按动作过滤
  ├─ ns.action=OPEN/ADD → 拦截（不允许新开仓/加仓）
  ├─ ns.action=REDUCE/CLOSE → 放行（允许减仓/平仓以保护用户资金）
  └─ bot 状态本身不改变（paused/active 保持），仅信号路由层过滤
```

---

## 6. 关键流程(文字版时序)

### 6.1 用户注册激活

```
POST /v1/auth/register {email,password} ──▶ auth-svc ──▶ mailer 发送 6 位验证码(5min)
POST /v1/auth/verify-email {code} ──▶ auth-svc ──▶ User.is_active=true ──▶ JWT
POST /v1/identity/choose-exchange {exchange} ──▶ identity-svc ──▶ Identity 行
POST /v1/identity/bind-exchange-invite {code} ──▶ ★ G27 交易所邀请码核实（必填）
   ├─ 码存在 + 启用 + 未达上限 + 属于所选所 ──▶ Identity.exchange_invite_code 绑定 ──▶ audit-log
   └─ 任一失败 ──▶ 拒绝并提示具体原因（码不存在/已停用/已达上限/非本所码）
POST /v1/identity/bind-invite {code} ──▶ referral-svc ──▶ Invite(locked=true)（好友码，可选）
```

### 6.2 API 绑定实时校验

```
POST /v1/apikeys {exchange,key,secret} ──▶ apikeys
   ├─ ExchangeAdapter.test_connect() 网络连通?
   ├─ fetch_balance() 密钥正确?
   └─ api_permissions: read=1 AND trade=1 AND withdraw=0?
         ├─withdraw=1 ─▶ 拒绝("禁止绑定带提现权限的 API")
         └─通过 ─▶ api-vault.encrypt ─▶ ApiKey 入库
失败不入库,前端弹具体文案。
```

### 6.3 信号采集 → 策略匹配 → 独立机器人跟单

```
[adapters/scraper] 定时 ──▶ RawSignal
[normalizer] 解析 ──▶ NormalizedSignal(action=OPEN/ADD/REDUCE/CLOSE) ──▶ dedupe_key
   ├─已存在 ─▶ 丢弃
   └─新 ─▶ SourceSignal 入库(dropped=false)
[signal-store] Redis Pub/Sub `signal.new`
[copy-engine] 拉取所有 active+未订阅过期的 CopyBot 且 strategy_id 匹配
   ├─无匹配 ─▶ END
   └─有匹配 ─▶ ★ G03：按 ns.action 路由
        ├─OPEN  → 走完整 USDT 4 步换算 ─▶ OrderIntent
        ├─ADD   → 检查 max_total_position → 换算增量 ─▶ OrderIntent
        ├─REDUCE → 按比例减仓 ─▶ OrderIntent
        └─CLOSE  → 全部平仓 ─▶ OrderIntent
        ★ G10 预留：订阅过期时仅放行 REDUCE/CLOSE，拦截 OPEN/ADD
★ G21 前端画像兜底：策略详情接口返回 profile 时
   ├─今日已同步 ─▶ 返回当日 snapshot + is_stale=false
   ├─今日未同步 ─▶ 返回 last_good_snapshot + is_stale=true ("数据更新于昨日")
   └─无任何历史 ─▶ 返回 null + placeholder=true ("数据同步中，请稍后查看")
[risk-engine] evaluate(intent) ─▶ RiskDecision
   ├─rejected ─▶ CopyOrder(failure_category=risk) ─▶ END
   └─approved ─▶ Celery 队列 ─▶ [executor] 
        ★ G07：下单前 set_margin_mode(bot.margin_mode) + set_leverage(bot.leverage)
        ─▶ 官方直连下单(ExchangeAdapter) ─▶ ExecutionReport
        ├─success ─▶ CopyOrder.status=filled ─▶ trade-tracker WS 对账
        └─failure ─▶ failure_category 分类 ─▶ 1 次失败不重试
[trade-tracker] ─▶ PositionSnapshot 更新 ─▶ WS /ws/stream 推送
```

### 6.4 USDT 本位换算 4 步法

> **G08 修复**：合约面值/最小开仓量/精度均从 `ContractSpec` 表按 `exchange + symbol` 查询，不再使用交易所级别参数。`NormalizedSignal.contract` 字段在标准化阶段已关联填充。

```
输入：CopyBot.config + NormalizedSignal(含 ns.contract: ContractSpec)
Step1 target_notional_usdt =
        fixed → bot.fixed_amount_usdt
        percent → account.free × bot.percent/100
Step2 contract_face_value_usdt = ns.contract.face_value_usdt   ← 合约级面值
Step3 qty_raw = target_notional_usdt / contract_face_value_usdt
        qty_raw ≥ ns.contract.min_size → qty = floor(qty_raw, decimals=ns.contract.size_precision)
        qty_raw < ns.contract.min_size → qty = min_size(向上补足,记日志)
Step4 required_margin_usdt = qty × face_value / leverage
Pre-submit 校验：required_margin_usdt ≤ account.free
        └─否 ─▶ failure_category='balance'
→ 输出 (qty, required_margin_usdt)
→ ★ G07：下单前调用 OrderRouter.set_margin_mode(symbol, bot.margin_mode) + set_leverage(symbol, bot.leverage)
```

### 6.5 链上支付自动校验(含阈值)

> ★ G09：本流程为三链统一实现（web3.py for TRC/BEP/ERC + tronpy for TRON）。

```
POST /v1/payments/{order_id}/submit-tx {tx_hash,network}
Step1 instant_verify
   ├─network == order.network?
   ├─to_address == expected_to_address?
   ├─value ≥ order.amount_usdt?
   └─tx.status == 'success'?
     全部通过 ─▶ status='verifying' → Step2
      任一失败 ─▶ status='failed',前端报错 END
Step2 schedule poll (1/5/10/20 min)
   ├─poll_attempts += 1
   ├─get_confirmations(tx_hash)
   ├─confirmations ≥ required_confirmations ─▶ status='confirmed' ─▶ billing.activate ─▶ mailer
   ├─连续 3 次 API 错 ─▶ status='manual'
   ├─poll_attempts ≥ 6 ─▶ status='manual'
   └─完成 4 轮仍不足 ─▶ status='timeout' ─▶ mailer + 异常池
Step3 (admin 介入): "强制确认开通" ─▶ status='confirmed'
```

### 6.6 邀请奖励触发 → 24h 核实 → 状态流转

```
Subscription.verifying → active (PaymentOrder confirmed)
   ▼
referral-svc.should_trigger_reward(order)
   ├─invitee.identity_type != 'sub_account' ─▶ true
   ▼
ledger-svc.credit(owner=inviter, source='referral', amount=order.amount*0.10)
   ├─★ G11 修复：检查风控标记
   │   risk_flag = referral.detect_batch_abuse(inviter, window=1h)
   │   if risk_flag.is_flagged → verifying_hours=48 (延长核实)
   │   else → verifying_hours=24 (正常核实)
   ├─Reward.status='verifying'
   ├─verifying_started_at=now, verifying_ends_at=now + {verifying_hours}h
   ├─24h 内下级退款/回滚 ─▶ status='canceled'
   ▼
24h 后 Celery beat 扫描
reward.scan_verifying()
   ├─now ≥ verifying_ends_at AND no refund ─▶ status='available'
   └─now ≥ verifying_ends_at AND refund ─▶ status='canceled'
```

### 6.7 提现申请 → 人工审核 → TxHash 验证 → 发放

```
POST /v1/withdrawals {amount,network,address}
   ├─balance ≥ 10U + amount ≤ 可提现 + 1U 手续费
   ├─address 正则(TRC20: ^T[1-9A-HJ-NP-Za-km-z]{33}$; BEP20: ^0x[0-9a-fA-F]{40}$)
   └─成功 ─▶ status='pending_review'
   └─ledger：N 条 Reward 标记为 'withdrawing'(可提现 → 提现中)

管理员 /admin/v1/withdrawals/{id}/approve ─▶ status='approved'
管理员 /admin/v1/withdrawals/{id}/fill-tx {tx_hash} ─▶ verify_onchain
   ├─valid ─▶ status='paid' ─▶ mailer ─▶ ledger 'withdrawing' → 'paid'
   └─invalid ─▶ status='paid_failed' ─▶ 管理员可 retry/refund

管理员 /admin/v1/withdrawals/{id}/reject {reason} ─▶ status='rejected' ─▶ ledger 'withdrawing' → 'available'
```

### 6.8 跨所错配拦截

```
用户点击"开启跟单" strategy_id=X
   ▼
copy-engine.on_enable_click(strategy_id, user_id)
   ├─Identity.identity_type IN ('normal' 已订阅 / 'sub_account')?
   ├─ApiKey 存在且 active 且 exchange = strategy.source_exchange?
   │     └─缺 ─▶ 前端弹窗："该策略信号来自 [交易所],未绑定该所 API"
   └─通过 ─▶ CopyBot 配置页(杠杆/比例/最大仓位/★G07:逐仓/全仓 margin_mode)
失败任一：拒绝进入配置页 +记 audit-log。
```

---

## 7. 接口契约(REST 骨架)

### 7.1 用户前台 `/v1/*`

| Method | Path | 说明 |
|---|---|---|
| POST | /v1/auth/register | 邮箱注册 |
| POST | /v1/auth/verify-email | 验证码激活 |
| POST | /v1/auth/login | 登录 → TokenPair |
| POST | /v1/auth/logout | 注销 |
| POST | /v1/auth/reset-password | 重置密码 |
| GET | /v1/identity/me | 当前身份 |
| POST | /v1/identity/choose-exchange | 选择所属所 |
| POST | /v1/identity/bind-invite | 绑定邀请码（好友） |
| POST | /v1/identity/bind-exchange-invite | ★ G27 绑定交易所邀请码（核实有效性） |
| GET | /v1/apikeys | 已绑定 API |
| POST | /v1/apikeys | 绑定(写时加密) |
| DELETE | /v1/apikeys/{exchange} | 解绑 |
| POST | /v1/apikeys/{exchange}/recheck | 重新校验 |
| GET | /v1/strategies | 策略广场(分页/筛选/排序) |
| GET | /v1/strategies/{id} | 策略详情(含画像) |
| GET/POST/PATCH/DELETE | /v1/bots[/...] | 跟单机器人 CRUD |
| POST | /v1/bots/{id}/{pause,resume} | 暂停/恢复 |
| GET | /v1/subscriptions/me | 当前订阅 |
| GET | /v1/subscriptions/plans | 套餐列表 |
| POST | /v1/subscriptions | 发起订阅 |
| POST | /v1/payments/{order_id}/submit-tx | 提交 TxHash |
| GET | /v1/payments/{order_id} | 订单状态 |
| GET | /v1/referrals/me | 我的邀请码 + 列表 |
| GET | /v1/rewards/me | 奖励余额(5 字段:累计/可提现/提现中/已提现/冻结) ★G25 校正 |
| GET | /v1/rewards | 奖励流水 |
| POST/GET | /v1/withdrawals | 提现申请/记录 |
| GET | /v1/account/overview | 首页 4 卡数据 + has_api/has_bot 标志(★G23 新手引导判定) + 金额支持隐藏/显示(★G22) |
| GET | /v1/strategies/{id} | 策略详情(含画像,返回 is_stale/placeholder 兜底标志 ★G21) |

### 7.2 实时通信 `/ws/stream`

WSS;JWT in subprotocol 或 query;帧 `{channel, payload}`。

- `strategy.update` 策略画像
- `signal.new` 新信号(仅当用户有匹配 bot 时推送)
- `bot.position` / `bot.order` 仓位与下单
- `pnl.tick` / `account.balance` 盈亏/余额实时
- `reward.tick` 奖励状态(含 24h 倒计时)
- `withdrawal.status` 提现状态

### 7.3 后台 `/admin/v1/*`

| Method | Path | 对应模块 |
|---|---|---|
| POST | /admin/v1/auth/login | 后台登录 |
| GET | /admin/v1/users | 用户管理 |
| POST | /admin/v1/users/{id}/{freeze,unfreeze,mark-sub-account} | 风控/标记 |
| GET | /admin/v1/review | 主号下级审核 |
| POST | /admin/v1/review/{id}/{approve,reject} | 审核动作 |
| GET | /admin/v1/signals/{exchange} | 按所物理隔离 |
| GET/POST | /admin/v1/signals/{exchange}/{candidate,listed} | 待选/已添加 |
| POST | /admin/v1/signals/{exchange}/{id}/{add,pause,resume,delist} | 上下架 |
| GET | /admin/v1/signals/{exchange}/listed/logistics | ★G26 运维看板:source_mode(模式A/B) + 子账户ID + 实时余额 + WS状态(在线/重连/离线);模式B字段 V2 启用,结构预留 |
| GET | /admin/v1/orders | 全平台订单监控 |
| GET | /admin/v1/orders/failures | 失败归类报表 |
| GET | /admin/v1/payments | 支付订单列表 |
| POST | /admin/v1/payments/{id}/manual-confirm | 强制确认 |
| GET | /admin/v1/invites | 邀请关系 |
| GET | /admin/v1/invites/risk | 风控看板 |
| GET/POST | /admin/v1/exchange-invites | ★ G27 交易所邀请码列表/新增 |
| PATCH | /admin/v1/exchange-invites/{id} | ★ G27 启停用（写 audit-log） |
| GET | /admin/v1/wallets | 奖励流水 |
| POST | /admin/v1/wallets/{reward_id}/{credit,debit} | 手动补发/扣除 |
| GET | /admin/v1/withdrawals | 提现审核列表 |
| POST | /admin/v1/withdrawals/{id}/{approve,reject,fill-tx,retry,refund} | 审核操作 |
| GET/PATCH | /admin/v1/risk/{rules,strategies/{id}} | 全局/策略级风控参数 |
| GET | /admin/v1/audit | 审计日志 |

---

## 8. 关键安全约束

1. **用户 API key 加密**：AES-256-GCM;nonce=12B;tag=16B;AAD 绑 `user_id|exchange|key_id`;主密钥经 `MASTER_KEY_B64` 注入,预留 KMS。
2. **拒绝提现权限**：绑定时强制探测 `withdraw=false`,发现直接拒绝,绝不入库。
3. **后台完全隔离**：独立登录入口、独立 cookie 域、独立 JWT audience、`role=admin` 双因素(V1.1 后置 TOTP)。
4. **审计留痕**：所有后台写操作必填 actor/action/target/before/after/reason/ts;用户关键动作(绑定/解绑 API、提现申请、修改密码)也留痕。
5. **邀请永久锁定**：`locked=true`;管理员特权修改需 before/after + reason + 写 audit-log。
6. **防循环邀请**：`bind_invite_code` 中实现祖先链回溯,禁止出现 A→B→A 或更长环。
7. **提现地址校验**：前端正则 + 后端正则 + (V2) 黑/白名单。
8. **支付阈值硬编码**：TRC-20=12、BEP-20=15、ERC-20=12;不开放配置。
9. **单笔订单查询 ≤6 次**：即时校验 1 + 4 次轮询 + 1 兜底 = 6 上限;触顶转人工。
10. **错误信息脱敏**：禁止返回原始 API key、密码、完整地址(保留前 4 后 4)、调试堆栈外泄。
11. **强制风险揭示**：注册成功首次开启跟单必须勾选"我已阅读并同意"模态框。
12. **CSRF/XSS/SQLi**：Pydantic 校验 + 参数化 SQL + SameSite=Lax + CSP + CORS 白名单。

---

## 9. 风险与合规

| 风险 | 影响 | 应对 |
|---|---|---|
| 5% 返佣/利润分成被认定为金融服务 | 监管合规 | 仅订阅费收入;不抽水不分润;前台明示 |
| 爬虫延迟导致滑点 | 用户亏损 | 模式 A >10s 丢弃;模式 B >5s 丢弃;限价单保护 |
| 多源信号重复 | 重复跟单 | dedupe_key UNIQUE + 虚拟账本防双开 |
| 单笔订单查询被刷光 | 资源耗尽 | ≤6 次硬上限 |
| 用户 API key 泄漏 | 资产损失 | AES-256-GCM + 拒绝提现权限 + 不入日志 + (V2) IP 白名单 |
| 用户邀请刷单 | 平台亏损 | 批异常检测 + 48h 延长 + 提现冻结 |
| 跨所错配 | 下单失败 | 开启跟单前强校验 |
| 公开排行榜反爬 | 数据缺失 | Playwright + 代理池 + 退化为官方 API |
| 数字货币地址错误 | 资产永久丢失 | 正则 + (V2) 白名单 + 人工二次确认 |
| 订单失败重试死循环 | 极端行情爆仓 | 严格 1 次失败不重试 + 精确归因 |
| 后台越权 | 资产损失 | RBAC + audit-log + 二次确认 |
| 用户/管理员登录混用 | 横向越权 | 完全隔离入口 + cookie + audience |

合规策略要点：V1 严守"工具平台"定位;合规文案、免责条款、风险揭示模态框强制;不做投顾建议。

---

## 10. 与 gate_copy_trading 的关系

### 10.1 边界

| 维度 | gate_copy_trading | signal-saas(本平台) |
|---|---|---|
| 交易所覆盖 | Gate.io 单所 | 5 家 CEX |
| 信号采集 | 1 种(Playwright) | 2 种(V1 公开爬虫 / V2 小号 WS),预留 5×2 |
| 用户模型 | 单用户 / 单 API key | 多租户 + 多 API key 凭证保险库 |
| 跟单对象 | 自身账户"信号机器人" | 用户维度"独立跟单机器人" + 独立虚拟账本 |
| 注册/订阅 | 无 | 完整邮箱注册 + 验证码 + 套餐 + 链上支付 |
| 邀请/奖励/提现 | 无 | 完整 SaaS 计费体系 |
| 后台/审计 | 无 | Next.js 后台 10 模块 + audit-log |
| 数据存储 | SQLite | PG + TimescaleDB + Redis + Celery |
| 部署 | 本地脚本 | Docker Compose → k8s |
| 可观测性 | loguru | Prometheus + Grafana + OTel |

### 10.2 可借鉴点

- **Gate.io HMAC-SHA512 鉴权签名** → `exchange_clients/gate_adapter.py` 官方直连参考。
- **WS 重连/心跳/序列号** → 模式 B 小号 WS 实现时借鉴 cookies 会话保持。
- **CircuitBreaker + BalanceGuard + TraderFilter** 三件套思路 → `risk-engine/rules/` 工程化模板。
- **浏览器持久化 profile** → 排行榜爬虫可参考。

### 10.3 与 signal-aggregator 框架的关系

`signal-aggregator`(2026-08-11 框架文档)是 V2 多交易所抽象层,已定义 `AbstractExchangeAdapter / RawSignal / NormalizedSignal / Redis Streams topic`。本平台 V1 走"5 家官方直连",未来可平滑迁移：

- 把 `exchange_clients/*_adapter.py` 统一实现 `AbstractExchangeAdapter`。
- 把 `signal-store` 入队主题统一为 `signal.raw.received.v1` / `signal.normalized.v1`。
- 执行层已抽象 `ExchangeAdapter`,新增所只需补一个 adapter,**不必重写**。

---

## 11. 迭代路线(不含时间)

### V1.0 5 家交易所执行闭环(MVP)

- 脚手架：FastAPI + Next.js × 2 + PG + Redis + Celery + Docker Compose。
- 业务：邮箱注册 / 验证码 / 选所属所 / 绑邀请码 / 绑 5 家 API(拒提现)。
- 订阅：5U 试用限购 1 次 / 19.9U 正式;TRC-20 + BEP-20 支付 + 阈值校验。
- 跟单：公开爬虫 → 标准化 → 包装策略 → CopyBot → USDT4 步 → 官方直连(ExchangeAdapter) → 私有 WS 回报。
- 邀请/奖励：10% 现金 + 24h 核实 + 流水账。
- 提现：TRC-20 + BEP-20 + 10U 起提 + 1U 手续费 + 人工审核 + TxHash 校验。
- 后台 10 模块全部最小可用。
- 风控：白名单 / 单 bot 名义上限 / 延迟红线 10s / 跨所拦截。

### V1.1 扩展新所

- 执行层已抽象 `ExchangeAdapter`,新增所只需补官方客户端,**不必重写**。
- identity 选所改为可切换;用户可同时绑多所各 1 个 API。
- 订阅/支付/提现/邀请逻辑零改动。

### V1.2 Bitget + Binance

- 补齐 4/5 家 adapter;策略广场多源化。
- 引入"风险评级/策略风格"过滤;按交易所分组(仅后台可见)。

### V2.0 模式 B 小号 WS / 多链 ERC-20 提现 / 地址白名单

- `adapters/*/ws_mini.py` 落地;引入小号池管理 + 平台保证金占用。
- 延迟从 8s 级降到 2s 级;小号模式信号可"超低延迟"标签。
- 提现新增 ERC-20 + 地址白名单(V2.1 后置可)。
- KMS 主密钥 + 定期轮换;后台二次确认 +留痕升级。

### V2.x 高级能力

- 信号评分 / Trader 排行榜 / 回测框架 / 紧急制动 / 灰度发布 / 多语言 / 多币种结算。

---

## 12. Verification(核心流程自洽示例)

### 12.1 USDT 本位换算(Python 伪代码)

```python
def compute_size(bot, ns, account):
    """G08 修复：精度参数从 ns.contract（合约级）获取，不再传 exch（交易所级）"""
    if bot.amount_mode == 'fixed':
        target = bot.fixed_amount_usdt
    else:
        target = account.free * (Decimal(bot.percent) / Decimal(100))
    contract = ns.contract                        # ContractSpec（合约级）
    face = contract.face_value_usdt
    qty_raw = target / face
    min_size = contract.min_size                  # ← 合约级最小开仓量
    precision = contract.size_precision            # ← 合约级精度
    if qty_raw < min_size:
        qty = min_size                          # 向上补足
    else:
        qty = qty_raw.quantize(Decimal(10) ** -precision, rounding=ROUND_FLOOR)
    margin = qty * face / Decimal(bot.leverage)
    if margin > account.free:
        raise InsufficientBalance(qty, margin, account.free)
    return qty, margin
```

### 12.2 订阅放行(SQL 视角)

```sql
SELECT s.status, s.expires_at, i.identity_type
FROM subscription s JOIN identity i ON i.user_id = s.user_id
WHERE s.user_id = :uid AND s.plan_id = :plan_id
ORDER BY s.created_at DESC LIMIT 1;
-- 判定：
-- 1) identity_type='sub_account' → 直接 active
-- 2) status='active' AND now()<expires_at → active
-- 3) 试用唯一性：count(*) WHERE plan_id='trial_5u' AND status IN ('active','expired') ≤ 1
```

### 12.3 奖励 24h 状态机扫描

```python
@celery.task
def sweep_rewards():
    now = utcnow()
    # verifying → available / canceled
    rs = Reward.objects.filter(status='verifying', verifying_ends_at__lte=now)
    for r in rs:
        order = r.source_payment_order
        if order.status == 'confirmed' and not has_refund(order):
            r.status = 'available'; r.available_at = now
        else:
            r.status = 'canceled'
        r.save()
    # 后置回滚
    for ev in RefundEvent.objects.filter(processed=False):
        for r in Reward.objects.filter(source_payment_order_id=ev.order_id,
                                        status__in=['available','withdrawing','paid']):
            ledger.rollback(owner_id=r.owner_id, ref_id=r.id, reason=f"refund {ev.order_id}")
            r.status = 'rolled_back' if r.status == 'paid' else 'canceled'
            r.save()
        ev.processed = True; ev.save()
```

### 12.4 支付自动校验

```python
@celery.task(bind=True, max_retries=0)
def poll_payment(self, order_id):
    o = PaymentOrder.objects.get(id=order_id)
    if o.status not in ('verifying','polling'):
        return
    o.poll_attempts = (o.poll_attempts or 0) + 1
    if o.poll_attempts > 6:
        o.status = 'manual'; o.save(); return
    conf = chain_client.get_confirmations(o.network, o.tx_hash)
    o.confirmations = conf
    if conf >= o.required_confirmations:
        o.status = 'confirmed'; o.save()
        billing.activate(o.user_id, o.plan_id, o.id)
        mailer.send(o.user.email, 'payment_ok', {...})
    else:
        schedule_next_poll(o)
        o.save()
```

### 12.5 风控前置

```python
async def evaluate(user_id, bot, intent, signal):
    if not risk.whitelist.contains(bot.strategy_id):
        return reject("strategy not whitelisted")
    projected = bot.virtual_locked_usdt + intent.required_margin_usdt * intent.leverage
    if projected > bot.max_total_position_usdt:
        return reject("bot position cap reached")
    if risk.global_throttle(intent.exchange) > MAX_CONCURRENT:
        return reject("global throttle")
    age_ms = (utcnow() - signal.received_at).total_seconds() * 1000
    if signal.source_mode == 'A' and age_ms > 10_000:
        return reject("mode A age > 10s")
    if signal.source_mode == 'B' and age_ms > 5_000:
        return reject("mode B age > 5s")
    if signal.symbol != intent.symbol:
        return reject("symbol mismatch")
    return approve(intent)
```

### 12.6 端到端串接

```
signal arrived ─▶ normalizer.dedupe ─▶ source_signal.insert ─▶ Redis pub `signal.new`
   ─▶ copy-engine.pull_matching_bots ─▶ per_bot.usdt_sizer ─▶ risk_engine.evaluate
   ─▶ executor.place ─▶ copy_order.update ─▶ trade_tracker.attach_ws
   ─▶ execution_report.fill ─▶ position_snapshot.update ─▶ ws push to user
全链路由 `trace_id` 串联,可在 audit-log 与 observability/tracing 中追溯。
```

---

## 文档结束

> 本文档为 V1.0 设计蓝本;所有具体实现将在后续 sprint 中按模块落地。任何字段、状态机、流程的二次变更必须先回写到本文档再实现。

**字数摘要**：约 14,000 中文字;12 章;18 张表(§4.2);5 张状态机图;8 段时序;3 大组 REST 接口(前台/WS/后台);21 个模块(后端 19 + 前端 2);18 张 ER 表(§4.1);6 段 Verification。