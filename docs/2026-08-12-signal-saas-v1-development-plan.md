# signal-saas V1 开发计划与里程碑

> **路径**：`c:\Users\w6485\Desktop\AI 量化\.trae\documents\2026-08-12-signal-saas-v1-development-plan.md`
> **基线文档**：[`2026-08-12-signal-saas-platform-design.md`](./2026-08-12-signal-saas-platform-design.md)（设计蓝本）+ [`2026-08-12-signal-saas-project-framework.md`](./2026-08-12-signal-saas-project-framework.md)（项目框架）+ [`2026-08-11-signal-aggregator-platform-framework.md`](./2026-08-11-signal-aggregator-platform-framework.md)（V2 抽象层）
> **对比结论**：[三方对比分析（saas vs aggregator vs gate_copy_trading）](#)（2026-08-12）
> **需求覆盖度核对**：[需求 1-10 章 × 设计覆盖度逐条核对表](./2026-08-12-signal-saas-requirements-coverage-check.md)（2026-08-12，62 项全 ✔）
> **范围**：V1.0 = 5 家交易所执行闭环（含全部 10 模块、计费、支付、邀请、提现、后台 10 模块）
> **决策 B**：执行层直接对接 5 家官方 API（弃用 ccxt）
> **数据截止**：2026-08-12
> **格式说明**：本计划按"里程碑 → 阶段任务 → 验收标准"三层组织；任务粒度控制在 1-3 天工作量级；不在此处写完整实现代码，**接口签名/SQL/状态机与设计蓝本严格对齐**。

---

## 0. 总览

### 0.1 战略定位（沿用对比结论）

- **V1 商业定位**：工具型 SaaS，订阅费单一收入；不抽水、不返佣。
- **技术边界**：V1 直连 5 家官方 API（决策 B，弃用 ccxt）；不走 signal-aggregator 抽象层；V1.1 再切换。
- **核心护城河**：邀请流水账 + 链上自动校验 + 后台审计 三件套。

### 0.2 里程碑总表（不含具体日期）

| 里程碑 | 名称 | 目标 | 累计工作量 |
|---|---|---|---|
| **M0** | 脚手架与基础设施 | 项目骨架、Docker Compose、CI、密钥保险库 | 1 周 |
| **M1** | 账号体系（无跟单） | 注册/验证码/登录/选所/绑邀请/绑 API/风险揭示 | 2 周 |
| **M2** | 信号采集 + 策略包装（后台） | Gate 爬虫、标准化、待选/已添加池、画像同步 | 3 周 |
| **M3** | 跟单引擎 + 风控（核心） | CopyBot、USDT 4 步换算、风控规则、官方直连执行 | 3 周 |
| **M4** | 订阅 + 支付 + 提现 | 套餐购买、TRC/BEP/ERC-20 三链校验、24h/48h 奖励、提现审核 | 3 周 |
| **M5** | 后台 10 模块 + 前台闭环 | 10 个后台页、首页数据看板、邀请/奖励/提现 UI | 3 周 |
| **M6** | 灰度 + 合规 + 上线 | 风险揭示强制、邀请风控、监控告警、压测、上线 | 2 周 |
| **合计** | | | **~17 周** |

> **决策 B（2026-08-12）**：执行层弃用 ccxt，直接对接 5 家官方 API。M3 新增 T3.0 官方客户端脚手架（2.5d），由 M3 缓冲吸收，总工期不变。

> **UI 蓝本（2026-08-12）**：前台 8 页 + 后台 11 页成品已交付，作为 M5 开发视觉蓝本。入口：[前台索引](./2026-08-12-signal-saas-ui-index.html) / [后台索引](./2026-08-12-signal-saas-admin-index.html)。M5 各任务按成品页实现，任务表已标注对应蓝本链接。

> **范围预留**：M0-M3 为"必修"；M4-M5 可拆分交付（M4 先最小可用，M5 后置）；M6 必须独立阶段。

### 0.3 团队建议

| 角色 | 人数 | 主要负责 |
|---|---|---|
| Tech Lead / 架构 | 1 | M0-M6 全程、Celery/Redis/PG 调优 |
| 后端工程师 | 2 | M1-M4（认证/计费/支付/跟单） |
| 前端工程师 | 2 | M1/M2/M4/M5（Next.js × 2） |
| 区块链工程师 | 1（可外包/兼职） | M4 链上支付/提现 |
| 测试 / QA | 1（共享） | M3-M6 |

---

## 1. 里程碑 M0 — 脚手架与基础设施（1 周）

### 1.1 目标

跑通"空 FastAPI 单体 + Next.js 双 SPA + PostgreSQL/Redis + Docker Compose"，实现 `hello-world` 跨前后端；CI 红绿基础。**单体架构**（非微服务）：21 个模块收敛为 `api/` 内包，见框架文档 §3。

### 1.2 阶段任务

| 任务 | 工期 | 验收标准 |
|---|---|---|
| T0.1 仓库初始化与目录骨架 | 0.5d | `signal-saas/` 按**框架文档 §3** 生成 `api/` 单体目录（core/db/models/schemas/routers/services/workers/ws）+ `web-ui/web-admin`；`pyproject.toml` 与 `package.json` 完成 |
| T0.2 Docker Compose 基础设施 | 1d | `postgres`、`redis`、`mailhog`(SMTP 调试)、`prometheus`、`grafana` 可起；`/healthz` 通 |
| T0.3 FastAPI 骨架 + OpenAPI | 1d | `GET /healthz`、`GET /v1/meta` 返回服务名/版本；自动生成 `/docs` |
| T0.4 Next.js × 2 前端骨架 | 1d | `web-ui` 与 `web-admin` 各自 `pnpm dev` 起；调用 `/healthz` 显示绿色 |
| T0.5 AES-256-GCM 凭证保险库（基础） | 1d | `ApiKeyVault.encrypt/decrypt` 单测通过；KMSProvider ABC 已留 |
| T0.6 密钥管理与启动校验 | 0.5d | `MASTER_KEY_B64` 缺失/长度错时启动失败；日志中**禁止**出现密钥明文 |
| T0.7 CI（lint + 单测空跑） | 0.5d | GitHub Actions / GitLab CI 跑通 ruff + mypy + pytest（允许空测） |
| T0.8 监控可观测基础 | 0.5d | `/metrics`（Prometheus）暴露；`/healthz`/`/readyz` 双探针 |

### 1.3 关键产出

```
signal-saas/
├── api/                    # FastAPI 单体后端（唯一后端，21 模块收敛为包）
├── web-ui/                 # Next.js 14 用户前台
├── web-admin/              # Next.js 14 后台
├── deploy/
│   ├── docker-compose.yml
│   ├── prometheus/
│   ├── grafana/
│   └── nginx/
├── tests/                  # 跨模块共享 fixtures
├── pyproject.toml
├── .env.example
└── README.md
```
> ★ 单体化：移除旧 `auth-svc/ ... 21 modules` 平铺目录；完整目录见 `2026-08-12-signal-saas-project-framework.md` §3。

### 1.4 验收门

- [ ] `docker compose up` 后 `curl localhost:8000/healthz` 返回 200
- [ ] `curl localhost:3000` 与 `curl localhost:3001` 都可访问
- [ ] 启动错误（缺密钥）时进程退出码非 0，且日志不含密钥
- [ ] CI pipeline 绿
- [ ] Grafana 可连接 Prometheus 看到 0 指标

---

## 2. 里程碑 M1 — 账号体系（无跟单）（2 周）

### 2.1 目标

完成"邮箱注册 → 验证码 → 登录 → 选所属所 → 绑邀请码 → 绑 API（拒提现）"全链路。前端完成注册/登录/个人中心/账户安全页。**不包含任何跟单/计费/支付**。

### 2.2 阶段任务

| 任务 | 工期 | 验收标准 |
|---|---|---|
| T1.1 数据模型：User / Identity / Invite / PlatformPool / ExchangeInviteCode | 0.5d | Alembic 迁移成功；User 邮箱 CITEXT UNIQUE；Identity 一对一；★G06: PlatformPool 表(invite_code UNIQUE, exchange, label, is_active)；★G27: ExchangeInviteCode 表(exchange, code, status, remark, bind_count, max_binds, UNIQUE(exchange,code)) |
| T1.2 AuthService：register + verify_email + login + logout | 2d | 邮箱+6 位码(5min TTL)+bcrypt 密码；JWT 签发/校验；refresh token |
| T1.3 mailer 模板 + NotificationService（SMTP / 站内消息） | 0.5d | 验证码邮件 HTML 模板；Mailhog 可收到；NotificationService 通过 WS 推送站内消息 |
| T1.4 IdentityService：choose_exchange + bind_invite_code + bind_exchange_invite + auto_detect_platform_pool | 2.5d | 防循环邀请（祖先链回溯）；一次性绑定；audit-log 写入；★G06: 绑定邀请码时自动检查 PlatformPool 表，命中且交易所匹配 → 自动标记 sub_account；★G27: bind_exchange_invite 核实（码存在+启用+未达上限+属于所选所，任一失败返回具体原因，成功 bind_count+1） |
| T1.5 ApiKey 绑定（含实时校验） | 2d | ExchangeAdapter.test_connect + fetch_balance + permissions；withdraw=1 拒绝；3 失败原因细分 |
| T1.6 ApiKeyVault 加密落库 | 0.5d | AES-256-GCM；AAD 绑 user_id\|exchange\|key_id；解密后即用即丢 |
| T1.7 强制风险揭示模态 | 0.5d | 首次登录 + 首次开启跟单两处强制勾选 |
| T1.8 前端：注册/登录/个人中心/账户安全 | 2d | Next.js 表单 + react-query；地址/密钥正则 |
| T1.9 强制风险揭示模态（前端） | 0.5d | 模态框+勾选+确认按钮；不勾选不可继续 |
| T1.10 audit-log 模块 + 关键操作记录 | 0.5d | 用户关键动作（绑/解绑 API、改密）写 audit-log |

### 2.3 关键接口

| Method | Path | 说明 |
|---|---|---|
| POST | /v1/auth/register | 注册 |
| POST | /v1/auth/verify-email | 验证码激活 |
| POST | /v1/auth/login | 登录 → TokenPair |
| POST | /v1/identity/choose-exchange | 选所 |
| POST | /v1/identity/bind-invite | 绑邀请 |
| POST | /v1/apikeys | 绑 API（写时加密） |
| DELETE | /v1/apikeys/{exchange} | 解绑 |

### 2.4 验收门

- [ ] 注册 → 收验证码 → 激活 → 登录 端到端通
- [ ] 选所后再调用选所返回 409
- [ ] 邀请码 A→B→A 触发循环校验拒绝
- [ ] ★G06: 填入 PlatformPool 中的邀请码 + 匹配交易所 → 自动标记 sub_account
- [ ] ★G06: 填入普通邀请码 → 保持 normal 身份，不触发自动标记
- [ ] 绑定带 withdraw 权限的 API 实时拒绝（不入库）
- [ ] audit-log 表中能查到用户每次绑定/解绑 + 自动标记记录
- [ ] 前端 4 个页面全部 200，强制风险揭示出现

---

## 3. 里程碑 M2 — 信号采集 + 策略包装（3 周）

### 3.1 目标

后台 M2 完成：Gate 公开爬虫 + 标准化 + 待选/已添加池 + 每日画像同步 + 5 大交易所标签页。前端 M2 完成：策略广场 + 策略详情。

### 3.2 阶段任务

| 任务 | 工期 | 验收标准 |
|---|---|---|
| T2.1 Gate 公开爬虫适配器 | 2d | Playwright + cookies 续期；`fetch_top_traders` / `fetch_trader_positions`；★反爬(需求 §2.10)：每个带单员资料页随机间隔 3-8s + 代理 IP 池轮换 |
| T2.2 信号标准化 + 去重 | 1d | `NormalizedSignal` 与设计蓝本一致；`dedupe_key = exchange\|trader\|sym\|side\|ts`；SQLite 内存缓存二级 |
| T2.3 数据模型：Trader / Strategy / SourceSignal / TraderProfile | 0.5d | Alembic 迁移；TraderProfile 按日快照；`signal.dedupe_key UNIQUE`；★G05: TraderProfile 增加 roi_90d, roi_all, win_rate_all, trading_days 字段 |
| T2.4 信号存储 + 异常丢弃 | 1d | 模式 A >10s 自动 drop；写入 Redis Pub/Sub `signal.new` |
| T2.5 后台"待选池"标签页（Gate） | 1d | 显示全量爬取数据；分页/搜索 |
| T2.6 后台"已添加池" + 策略包装 + ★G04 门槛校验 | 2d | 自定义前端名 + 风格 + 风险评级；下架/暂停；★G04: TraderSelectionPolicy(胜率≥55%/回撤≤30%/天数≥30) 上架前强制校验，force=true 可跳过但需填理由 + audit-log |
| T2.7 每日画像同步 Celery Beat | 2d | 凌晨 00:00-05:00 全量同步；连续 3 天失败告警；★G05: 同步内容包含 7d/30d/90d/累计 ROI + 最近 50 笔交易记录 + win_rate_all + trading_days |
| T2.8 5 大交易所标签页骨架（占位） | 1d | 后台顶部 Binance/OKX/Bybit/Bitget/Gate 切换；非 Gate 显示"待接入" |
| T2.9 前端策略广场 | 1d | 隐藏交易所 Logo/标签；筛选（风格/风险）；排序（跟单人数/7日收益/胜率） |
| T2.10 前端策略详情 | 1d | 实时持仓 + 7/30/历史收益曲线 + 最近 50 笔；占位"数据同步中" |
| T2.11 详情页缓存兜底 | 0.5d | 画像缺失时显示昨日数据 + 标注 |

### 3.3 关键事件流

```
[adapters/gate/scraper] → RawSignal
   ↓
[normalizer] → NormalizedSignal → dedupe_key
   ├─ 已存在 → 丢弃
   └─ 新 → SourceSignal 入库 → Redis pub `signal.new`
```

### 3.4 验收门

- [ ] Gate 公开排行榜持续 24h 采集无中断
- [ ] 后台 2 个池子能查看 / 添加 / 暂停 / 下架
- [ ] ★G04: 胜率 <55% 或回撤 >30% 或天数 <30 的带单员无法上架（force=true 可跳过但留痕）
- [ ] ★G05: TraderProfile 包含 roi_7d/30d/90d/all 四个时间段 + trading_days + win_rate_all
- [ ] 凌晨画像同步可在日志/Redis 中看到
- [ ] 前端策略广场不出现 Gate 字样；筛选/排序生效
- [ ] 模式 A 延迟 >10s 的信号在 `dropped` 表中可见

---

## 4. 里程碑 M3 — 跟单引擎 + 风控（核心）（3 周）

### 4.1 目标

完成"信号 → 策略匹配 → CopyBot 换算 → 风控前置 → 官方直连下单 → 成交回报 → 仓位/PnL 更新"全链路，含 5 条风控规则与失败归因。**这是产品核心，必须独立测试阶段**。

### 4.2 阶段任务

| 任务 | 工期 | 验收标准 |
|---|---|---|
| T3.0 官方客户端脚手架（决策 B） | 2.5d | `exchange_clients/` 5 家（Binance/OKX/Bybit/Bitget/Gate）`ExchangeAdapter` 抽象 + 签名/限流/合约规格；test_connect/fetch_balance/set_leverage/set_margin_mode/place/cancel 全接口；WS 心跳重连 |
| T3.1 数据模型：CopyBot / CopyOrder / PositionSnapshot / ContractSpec | 0.5d | Alembic 迁移；`virtual_locked_usdt` 字段；failure_category 枚举；★G07: CopyBot 增加 margin_mode(isolated/cross)；★G03: CopyOrder 增加 action(open/add/reduce/close)；★G08: ContractSpec 表(exchange, symbol, face_value_usdt, min_size, size_precision) UNIQUE(exchange,symbol) |
| T3.2 CopyBotService CRUD | 1d | create / update / pause / resume；跨所错配拦截前置 |
| T3.3 信号→机器人匹配（订阅 signal.new） | 1d | Redis pub/sub 订阅；按 strategy_id 拉活跃 bot |
| T3.4 USDT 本位换算 4 步法 | 1.5d | fixed/percent 模式；★G08: face_value/min_size/precision 从 ContractSpec 表按 exchange+symbol 查询（合约级）；min_size 向上补足；向下取整；margin 校验；★G07: 下单前 set_margin_mode + set_leverage |
| T3.5 5 条风控规则 | 2d | whitelist/position_limit/concurrency/daily_loss/emergency_stop；短路评估 |
| T3.6 OrderRouter（官方直连 + 滑点） | 2d | 经 ExchangeAdapter 下单；限价保护 = 价格 × (1±slippage_bps/1e4)；失败 1 次不重试 |
| T3.7 TradeTracker（私有 WS 回报） | 1.5d | attach/detach user；reconcile_position；realized/unrealized pnl |
| T3.8 失败归因 8 类 | 1d | balance/permission/leverage/symbol/min_size/network/price_deviation/slippage/other |
| T3.9 前端"我的跟单"机器人卡片 | 1d | 状态/盈亏/参数；暂停恢复按钮；修改配置弹窗 |
| T3.10 单测：换算 + 风控 + DiffEngine | 1d | 关键算法 100% 覆盖；mock ExchangeAdapter |

### 4.3 USDT 4 步换算（核心伪代码）

```python
def compute_size(bot, ns, account):
    """G08: 精度参数从 ns.contract（ContractSpec 合约级）获取"""
    target = bot.fixed if bot.amount_mode=='fixed' else account.free * bot.percent/100
    contract = ns.contract                           # ← ContractSpec 合约级
    face = contract.face_value_usdt
    qty_raw = target / face
    if qty_raw < contract.min_size:
        qty = contract.min_size                      # 向上补足
        audit_log('min_size_bumped', bot_id=bot.id)
    else:
        qty = qty_raw.quantize(Decimal(10)**-contract.size_precision, ROUND_FLOOR)
    margin = qty * face / bot.leverage
    if margin > account.free:
        raise InsufficientBalance(qty, margin, account.free)
    return qty, margin
# G07: 下单前调用 set_margin_mode(symbol, bot.margin_mode) + set_leverage(symbol, bot.leverage)
```

### 4.4 风控前置（核心伪代码）

```python
async def evaluate(user_id, bot, intent, signal):
    # ★ G03: 按信号动作类型校验
    if signal.action not in (SignalAction.OPEN, SignalAction.ADD,
                              SignalAction.REDUCE, SignalAction.CLOSE):
        return reject('unknown action')
    # ★ G10 预留: 订阅过期时拦截 OPEN/ADD，放行 REDUCE/CLOSE
    sub = await billing.get_active_subscription(user_id)
    if (not sub or sub.status != 'active') and bot.identity_type != 'sub_account':
        if signal.action in (SignalAction.OPEN, SignalAction.ADD):
            return reject('subscription expired, open/add blocked')
    if not whitelist.contains(bot.strategy_id): return reject('strategy not whitelisted')
    if bot.virtual_locked + intent.margin > bot.max_total_position: return reject('bot cap reached')
    if global_throttle(intent.exchange) > MAX_CONCURRENT: return reject('global throttle')
    age = (now() - signal.received_at).total_seconds() * 1000
    if signal.source_mode == 'A' and age > 10_000: return reject('mode A age > 10s')
    if signal.source_mode == 'B' and age > 5_000:  return reject('mode B age > 5s')
    if signal.symbol != intent.symbol: return reject('symbol mismatch')
    return approve(intent)
```

### 4.5 验收门

- [ ] 1 个测试用户在测试网绑定 Gate API + 1 个活跃 bot → 信号到达后能看到下单记录
- [ ] USDT 换算 4 个边界用例（fixed、percent、min_size 补足、超精度）单测全绿
- [ ] ★G08: ContractSpec 表中不同币种（BTCUSDT vs ETHUSDT）精度/面值独立生效
- [ ] ★G07: 下单日志中可见 set_margin_mode(isolated) + set_leverage 被调用
- [ ] ★G03: 4 种 action（OPEN/ADD/REDUCE/CLOSE）各有 1 个端到端用例
- [ ] ★G10: 订阅过期后 OPEN/ADD 被拦截，REDUCE/CLOSE 仍可执行
- [ ] 风控 5 条规则各 2 个用例（命中/未命中）
- [ ] 失败归因 8 类各 1 个 mock 用例
- [ ] 滑点保护：故意把信号价格改 1.5%，系统拒单
- [ ] 模式 A 延迟 >10s 自动 drop
- [ ] 跨所错配拦截：用户绑 Gate 想跟 OKX 信号，前端强弹窗

---

## 5. 里程碑 M4 — 订阅 + 支付 + 提现（3 周）

### 5.1 目标

完成订阅计费、链上支付自动校验、24h 奖励核实、提现审核。**这是合规核心，需独立测试与法务评估**。

### 5.2 阶段任务

| 任务 | 工期 | 验收标准 |
|---|---|---|
| T4.1 数据模型：Subscription / PaymentOrder / Reward / Withdrawal | 0.5d | Alembic 迁移；状态机字段；`dedup_key UNIQUE`；`poll_attempts ≤ 6` |
| T4.2 BillingService 套餐定义 | 0.5d | 5U 试用限购 1 次（DB 强校验）；19.9U 正式 |
| T4.3 PaymentService 即时校验 | 2d | to/value/status 三校验；★G09: 支持三链(TRC-20/BEP-20/ERC-20)即时校验；网络/链错误细分；任一失败拒绝 |
| T4.4 PaymentService 轮询（1/5/10/20 min） | 2d | Celery Beat 调度；TRC-20=12/BEP-20=15/ERC-20=12；超时 → manual |
| T4.5 ReferralService + LedgerService + ★G11 48h 风控延长 | 2.5d | 主号下级不触发；★G11: 风控高危用户核实期延长至 48h（detect_batch_abuse → verifying_hours=48）；流水账（不直接改 user 余额） |
| T4.6 WithdrawalService 申请 + 锁定 | 1d | ★G13: 最低提现门槛统一 10U（后台可配）；1U 手续费（实发=申请-1U）；地址正则（TRC/BEP）；锁定 → 提现中 |
| T4.7 WithdrawalService 人工审核 + 链上校验 | 2d | approve/reject/fill_tx/retry/refund 5 动作；链上校验 TxHash |
| T4.8 区块链 RPC 客户端 | 2d | ★G09: web3.py (ERC-20/BEP-20) + tronpy (TRC-20) 三链 get_confirmations 接口；ERC-20 GAS 估算复杂，工期 1.5d→2d |
| T4.9 风控：邀请刷单检测 | 1d | 1h 内 ≥N 个下级只买试用 → 标记 RiskFlag + 48h 延长 |
| T4.10 前端：套餐购买 / 提现申请 / 邀请码 | 2d | 选网络 → 收币地址 → 提交 TxHash → 状态轮询 |
| T4.11 前端：奖励余额 5 字段 + 倒计时 | 1d | ★G12: 累计/可提现/提现中/已提现/冻结 5 字段 + 24h/48h 倒计时 |
| T4.12 前端：提现表单 | 1d | 网络 + 地址正则 + 最低门槛提示 |

### 5.3 关键状态机

**支付订单**：

```
pending ─submitTxHash─▶ verifying
   ├─ 即时校验失败 ─▶ failed
   └─ polling ─▶ confirmations≥阈值 ─▶ confirmed ─▶ billing.activate
            ├─ 4 轮仍不足 ─▶ timeout
            ├─ API 连续 3 次错 ─▶ manual
            └─ poll_attempts ≥6 ─▶ manual
```

**奖励**：

```
verifying (24h) ─▶ available ─申请提现─▶ withdrawing
   │                  ├─ TxHash 通过 ─▶ paid
   │                  ├─ 链上失败 ─▶ paid_failed
   │                  └─ 审核拒绝 ─▶ available（退回）
   │ 24h 内下级退款 ─▶ canceled
paid ─下级事后退款─▶ rolled_back
```

**提现**：

```
可提现余额 ≥10U + 1U 手续费
   └─申请─▶ pending_review ─管理员审核─▶ approved
                                              ├─ 管理员转账成功+TxHash─▶ paid
                                              ├─ 转账失败 ─▶ paid_failed ─重试▶ approved
                                              ├─ 拒绝 ─▶ rejected
                                              └─ 退还 ─▶ refunded（资金回退）
```

### 5.4 验收门

- [ ] 5U 试用只能买 1 次（第二次前端隐藏/后端拒绝）
- [ ] ★G09: TRC-20/BEP-20/ERC-20 三链即时校验均通过；确认块 < 阈值时进入轮询
- [ ] 4 轮轮询后未达标自动进 manual
- [ ] 主号下级购买不会触发奖励
- [ ] 24h 倒计时归零后状态自动 available
- [ ] ★G11: 风控高危用户（1h 内批量试用）奖励核实期自动延长至 48h
- [ ] 下级事后退款，奖励记录自动 rolled_back，余额可扣到负值
- [ ] 1h 内 ≥N 个下级试用触发 RiskFlag
- [ ] ★G13: 最低提现门槛 10U 生效（非 5U）；实发=申请金额-1U
- [ ] ★G12: 奖励余额面板展示 5 字段（含冻结金额）
- [ ] 提现 TRC-20/BEP-20 正则错误前端拦截
- [ ] 管理员填 TxHash 后链上校验通过状态 → paid
- [ ] 单笔订单 API 调用 ≤6 次

---

## 6. 里程碑 M5 — 后台 10 模块 + 前台闭环（3 周）

### 6.1 目标

完成 web-admin 的 10 个模块 + web-ui 的首页/邀请/奖励/提现/账户安全**闭环整合**（★策略广场= M2 T2.9、策略详情= M2 T2.10、我的跟单= M3 T3.9 已在对应里程碑完成，M5 不重复开发）。

> 🎨 **视觉蓝本（2026-08-12 已交付）**：本里程碑全部页面的成品实现已存在，M5 按蓝本直接开发（样式/交互/布局完全对齐），下方任务表逐项标注蓝本文件。

### 6.2 阶段任务（后台 10 模块）

| 任务 | 工期 | 验收门 |
|---|---|---|
| T5.0 后台主框架 + 数据概览 | 1d | 240px 侧栏（10 模块）+ 顶部全局搜索 + 审计指示灯 + 6 KPI 卡 + 最近注册 + 审计日志流 + 今日待办。蓝本：[数据概览](./2026-08-12-signal-saas-admin-dashboard.html) |
| T5.1 后台登录（与前台完全隔离） | 1d | 独立入口/cookie/audience；TOTP 可后置。蓝本：[后台登录](./2026-08-12-signal-saas-admin-login.html) |
| T5.2 用户管理 | 1.5d | 列表+详情；冻结/解冻；身份标识。蓝本：[用户管理](./2026-08-12-signal-saas-admin-users.html)（含详情抽屉） |
| T5.3 主号下级审核 | 1d | 申请列表 + approve/reject + 留 audit-log。蓝本：[用户管理](./2026-08-12-signal-saas-admin-users.html)（主号标记区） |
| T5.4 信号源管理（5 所标签页） | 2d | 待选/已添加 + 上下架 + 暂停（已在 M2 完成主体，此处补运维列）。蓝本：[信号源审核](./2026-08-12-signal-saas-admin-signals.html)（含 ★G26 运维看板） |
| T5.5 订单监控 | 1.5d | 全平台下单 + 失败归类 + 延迟看板。蓝本：[跟单订单](./2026-08-12-signal-saas-admin-orders.html)（failure_category 九种归类） |
| T5.6 订阅与支付管理 | 1d | 订单列表 + 自动校验状态 + 手动确认。蓝本：[支付记录](./2026-08-12-signal-saas-admin-payments.html)（状态机 + 强制确认审计） |
| T5.7 邀请管理 | 1d | 关系列表 + 风控预警 + 修改日志。蓝本：[邀请奖励](./2026-08-12-signal-saas-admin-invites.html)（G11 批量滥用告警） |
| T5.8 奖励钱包 | 1d | 流水 + 手动补发/扣除 + 负值预警。蓝本：[钱包账本](./2026-08-12-signal-saas-admin-wallets.html)（5 字段 + 补发高危审计） |
| T5.9 提现审核 | 1d | 申请列表 + 5 动作 + TxHash 填入。蓝本：[提现审核](./2026-08-12-signal-saas-admin-withdrawals.html)（高危 48h 拦截） |
| T5.10 风控与系统设置 | 1d | 全局参数（最大杠杆、延迟红线）+ 策略级覆盖 + 提现配置。蓝本：[风控中心](./2026-08-12-signal-saas-admin-risk.html) |
| T5.11 系统日志 | 0.5d | 管理员操作 + 用户关键动作 + 支付审计。蓝本：[审计日志](./2026-08-12-signal-saas-admin-audit.html)（不可删除 + 变更前后高亮） |
| T5.12 RBAC + 二次确认 | 1d | role=admin/write 双层；高危操作需二次确认。蓝本：[后台登录](./2026-08-12-signal-saas-admin-login.html)（RBAC 三角色）+ 各高危弹窗 |
| T5.14 ★G27 交易所邀请码管理 | 1d | ExchangeInviteCode 表 + 每所多码 + 新增/启停用/绑定上限 + 审计。蓝本：[交易所邀请码](./2026-08-12-signal-saas-admin-exchange-invites.html) |

### 6.3 阶段任务（前台）

| 任务 | 工期 | 验收门 |
|---|---|---|
| T5.13 首页数据看板（4 卡） | 1.5d | 总资产/总持仓/今日收益/活跃跟单数；★G22 眼睛切换隐藏。蓝本：[首页看板](./2026-08-12-signal-saas-home-dashboard.html)（信号波 hero + 指标卡 + WS 模拟） |
| T5.14 首页"我的跟单"快速入口 + 新手三步引导 | 0.5d | 前 2-3 个机器人卡 + ★G23 无 API/无跟单时替换为新手引导。蓝本：[首页看板](./2026-08-12-signal-saas-home-dashboard.html)（onboard 3 步 + 机器人卡） |
| T5.15 邀请中心 | 0.5d | 专属码 + 邀请列表 + 24h 倒计时。蓝本：[邀请奖励](./2026-08-12-signal-saas-invite.html)（10% hero + 核实时间轴 + 收益趋势） |
| T5.16 奖励余额页 | 0.5d | ★5 字段（累计/可提现/提现中/已提现/冻结）+ 流水列表 + 状态标签。蓝本：[奖励余额](./2026-08-12-signal-saas-rewards.html)（G12/G25 5 字段账本） |
| T5.17 提现申请页 | 0.5d | 选网络 + 地址正则(34/42 位) + 余额校验 + 1U 手续费提示。蓝本：[提现](./2026-08-12-signal-saas-withdraw.html)（三链 + 实时到账计算 + 地址校验） |
| T5.18 个人中心 + 账户安全页 | 0.5d | 改密 + API 管理 + 风控冻结提示 + 账户概览（含交易所邀请码 G27 展示）+ 所属所切换。蓝本：[个人中心](./2026-08-12-signal-saas-account.html)（API 管理/选所/安全）+ [注册登录](./2026-08-12-signal-saas-auth.html) |
| T5.19 WSS 实时推送（8 频道） | 1.5d | strategy.update/signal.new/bot.position/bot.order/pnl.tick/account.balance/reward.tick/withdrawal.status。蓝本：各页内置 WS 模拟（首页 pnl.tick / 邀请 reward.tick / 详情 bot.position） |

> ★ 更正说明：策略广场、策略详情、我的跟单三个页面**已在 M2(T2.9/T2.10) 与 M3(T3.9) 完成**，M5 前台仅做首页闭环 + 邀请/奖励/提现/账户安全整合，**不重复开发**；T5.19 奖励余额为 5 字段（对齐 G12/G25）。相关成品蓝本：[策略广场](./2026-08-12-signal-saas-strategies.html) / [策略详情](./2026-08-12-signal-saas-strategy-detail.html) / [我的跟单](./2026-08-12-signal-saas-my-bots.html)。

### 6.4 验收门

- [ ] 后台 10 模块全部 200，RBAC 拒绝越权
- [ ] 首页 4 卡 WS 实时刷新
- [ ] ★G22 首页金额眼睛切换隐藏生效；★G23 无 API/无跟单时新手引导出现
- [ ] 邀请/奖励/提现三页强联动（邀请触发 → 24h → 可提现 → 申请 → 审核 → 发放）
- [ ] 所有管理员操作写入 audit-log
- [ ] ★奖励余额页展示 5 字段（含冻结）

---

## 7. 里程碑 M6 — 灰度 + 合规 + 上线（2 周）

### 7.1 目标

法务评估通过 + 监控告警就绪 + 压测通过 + 灰度发布。

### 7.2 阶段任务

| 任务 | 工期 | 验收门 |
|---|---|---|
| T6.1 法务评估（外包） | 3d | 5% 返佣规避、风险揭示文案、隐私政策合规 |
| T6.2 监控告警（Prometheus + Grafana） | 1d | 6 个核心指标 + 阈值告警 |
| T6.3 压测（Locust） | 1d | 100 并发用户持续 30min，p95 延迟 < 500ms |
| T6.4 安全审计 | 2d | 第三方白帽；AES-256-GCM + 防 SQLi + CSP |
| T6.5 灰度发布（白名单） | 2d | 前 50 用户手动审核；7 天观察期 |
| T6.6 备份与灾备 | 1d | PG 每日全量 + 增量；Redis AOF；密钥轮换演练 |
| T6.7 上线检查清单 | 0.5d | 配置/密钥/监控/降级开关全部就绪 |

### 7.3 6 个核心监控指标

| 指标名 | 类型 | 阈值告警 |
|---|---|---|
| `signal_received_total{exchange,source}` | Counter | 5min 跌 0 |
| `risk_decisions_total{decision}` | Counter | `rejected` 占比 >30% |
| `orders_placed_total{exchange,result}` | Counter | `failed` 占比 >10% |
| `payment_poll_attempts_total{network}` | Counter | >5 |
| `withdrawal_pending_total` | Gauge | >100 持续 1h |
| `http_request_duration_seconds` | Histogram | p95 > 1s |

---

## 8. 里程碑之间的依赖关系

```
M0 ──▶ M1 ──┬──▶ M2 ──▶ M3 ──┬──▶ M5 ──▶ M6
            │                  │
            └──▶ M4 ───────────┘
```

- M0 是所有阶段的前置
- M1 可与 M2 并行（M2 早期不依赖用户体系，只爬取公开数据）
- M3 必须在 M2 后（需要 SourceSignal 才能跟单）
- M4 可与 M3 并行（计费/支付/提现独立于跟单核心）
- M5 必须在 M3 + M4 都完成后（M5 整合）
- M6 是最终阶段

---

## 9. 横切关注点（贯穿所有里程碑）

| 关注点 | 关键约束 |
|---|---|
| **数据安全** | API key AES-256-GCM + 拒绝提现权限；日志中禁止密钥明文；CI 检查 |
| **合规** | 不抽水/不返佣；风险揭示模态强制；管理员操作 audit-log；后台与前台完全隔离 |
| **状态机完整性** | 每个状态机必须有 not-allowed-transition 保护（如已发放不能再审核） |
| **失败归因** | 8 类 failure_category 贯穿订单监控/失败告警 |
| **可观测** | 每个 svc 暴露 `/healthz` + Prometheus 指标；统一 trace_id 串联 |
| **测试** | 关键算法 100% 覆盖；Celery 任务必须 mock 或 integration 测试 |
| **法务** | M6 必须有外部法务评估；不得跳步 |

---

## 10. 关键文件清单（按里程碑）

### M0 产出

```
signal-saas/
├── pyproject.toml
├── api/main.py
├── api/deps.py
├── auth-svc/{api,models,service}.py
├── apikeys/{vault.py,service.py}
├── config/{settings.py,secrets.py}
├── observability/{logging,metrics,health}.py
├── deploy/docker-compose.yml
├── web-ui/{package.json,app/layout.tsx}
├── web-admin/{package.json,app/login/page.tsx}
├── tests/conftest.py
└── README.md
```

### M1 产出（增量）

```
├── users/{models.py,service.py,router.py}
├── identity/{service.py,router.py,pool_detector.py}   # ★G06: pool_detector.py
├── apikeys/{router.py,validation.py}
├── mailer/{smtp.py,templates/}
├── notification/{service.py,models.py}    # ★ 站内消息(WS 推送)
├── audit/{service.py,router.py}
└── web-ui/app/{register,login,account}/
```

### M2 产出（增量）

```
├── adapters/gate/{scraper,public_ws,parser}.py
├── adapters/base/{adapter.py,errors.py}
├── signal-normalizer/{model,parser,dedupe,worker}.py
├── signal-bus/{events,bus,topics}.py
├── signal-store/{models,repository,sync_profiles}.py
├── strategies/{service,router}.py
└── web-ui/app/strategies/
```

### M3 产出（增量）

```
├── copy-engine/{engine,sizer,bot_service,worker}.py  # ★G03: action 路由
├── risk-engine/{engine,rules/*}.py                      # ★G10: 过期拦截
├── executor/{vault,exchange_adapter,order_router,retry}.py  # ★G07: set_margin_mode 调用
├── trade-tracker/{ws_listener,position,pnl,reconciliation}.py
├── contract-spec/{models.py,sync_service.py}            # ★G08: ContractSpec 表 + 同步
├── bots/{router,service}.py
└── web-ui/app/bots/
```

### M4 产出（增量）

```
├── billing/{service,router}.py
├── payment/{service,chain_client,poller,router}.py
├── referral/{service,router}.py
├── ledger/{service,models}.py
├── withdrawal/{service,router,address_validator}.py
└── web-ui/app/{subscriptions,payments,invite,rewards,withdraw}/
```

### M5 产出（增量）

```
├── web-admin/app/{login,dashboard,users,review,signals,orders,
│                   payments,invites,wallets,withdrawals,risk,audit}/
├── web-admin/middleware/{auth,rbac}.py
└── web-ui/app/{page.tsx(首页4卡),account/overview}/
```

---

## 11. 风险与对策（沿用设计蓝本 §9，聚焦 V1）

| 风险 | 触发场景 | 对策 | 里程碑 |
|---|---|---|---|
| 链上支付误判为支付牌照 | 国内合规收紧 | 仅 USDT 收币；不碰法币；法务评估 M6 | M6 |
| 邀请刷单规模化 | 上线 1 周内 | M4 已带 RiskFlag；M6 灰度期重点盯 | M4 + M6 |
| Gate API 改版 | 突然断流 | 适配器层隔离；fallback 到 Playwright | M2 |
| 1h 内大规模并发跟单 | 名人带单员突然活跃 | 风控并发节流 + 紧急制动 | M3 |
| 提现地址错误导致资产损失 | 用户粘贴错地址 | 正则 + (V2) 白名单 | M4 |
| 管理员账号被盗 | 弱密码 | TOTP + IP 白名单 + 二次确认 | M5 |

---

## 12. 与对比结论的呼应

> 本节明确每个里程碑如何执行"差异化战略"。

| 差异化维度 | 来源对比结论 | V1 执行点 |
|---|---|---|
| 独立机器人 + 虚拟账本 | 与 gate_copy_trading 的单账户全局区分 | M3 T3.2 + T3.3 |
| 跨所错配拦截 | 三方均无 | M1 T1.5 + M3 T3.2 |
| 邀请奖励 24h 核实 + 流水账 | 三方均无 | M4 T4.5 |
| 链上支付自动校验 | 三方均无 | M4 T4.3 + T4.4 |
| 5 条风控规则 | gate_copy_trading 有 4 条；扩展 1 条 emergency_stop + invitation 监控 | M3 T3.5 + M4 T4.9 |
| 后台 10 模块 + 审计 | gate_copy_trading 仅 SQLite 审计 | M5 T5.1-T5.12 |
| AES-256-GCM 凭证 | gate_copy_trading 是 .env 明文 | M0 T0.5 + M1 T1.6 |
| 强制风险揭示 | gate_copy_trading 仅 README | M1 T1.9 |

### 12.1 需求第 1-10 章覆盖度核对结论

> 同步自 [`2026-08-12-signal-saas-requirements-coverage-check.md`](./2026-08-12-signal-saas-requirements-coverage-check.md)。**62 个功能点全部有设计对应，无致命缺失**；G21-G26 已于 2026-08-12 补齐。

| 需求章 | 功能点 | 覆盖 | 关键对应 |
|---|---|---|---|
| 1. 项目定位 | 5 | ✔ | §1.1 定位/合规/商业模式；★G24 用户画像 |
| 2. 信号源逻辑 | 11 | ✔ | 双轨制/门槛/两级池/画像；★G21 前端兜底 |
| 3. 用户注册与身份 | 4 | ✔ | 邮箱验证/主号下级/API 拒提现 |
| 4. 用户跟单逻辑 | 5 | ✔ | 配置/4 步换算/风控 |
| 5. 订阅收费逻辑 | 7 | ✔ | 三链支付/阈值/状态机 |
| 6. 邀请奖励逻辑 | 6 | ✔ | 10%/24h/48h 风控 |
| 7. 奖励余额系统 | 6 | ✔ | 5 字段账本/流水账 |
| 8. 提现逻辑 | 4 | ✔ | 10U 门槛/人工审核 |
| 9. 后台管理 | 11 | ✔ | 10 模块；★G26 运维看板 |
| 10. 前台页面 | 3 大节 | ✔ | 首页/策略广场/个人中心；★G22★G23 |

**本轮补齐的 G21-G26 落地里程碑**：

| 编号 | 缺口 | 落地里程碑/任务 |
|---|---|---|
| G21 | 前端画像兜底（is_stale/placeholder） | M2 T2.10 策略详情 + T2.11 缓存兜底 |
| G22 | 首页金额隐私小眼睛 | M5 首页数据看板 |
| G23 | 新手三步引导（has_api/has_bot） | M5 首页工作台 |
| G24 | §1.4 用户画像 | 设计蓝本 §1.1（已补，无开发任务） |
| G25 | 接口注释 5 字段校正 | M5 rewards 页 |
| G26 | 模式 B 运维看板字段预留 | M5 信号源后台（V2 启用字段） |

### 12.2 需求 1-10 章 → 开发计划任务落点映射表（全量核对）

> **核对结论：62 个功能点全部有开发任务落点，无遗漏、无重复。**（2026-08-12）

| 需求章 / 功能点 | 开发计划落点 |
|---|---|
| **1. 项目定位**（定位/合规/商业模式/画像） | 整体蓝图（M0-M6）；★G24 画像=设计 §1.1 |
| **2.1 信号源归属** | M2 后台两级池 |
| **2.2 双轨制**（模式A/B） | T2.1 爬虫(模式A) + 模式B=V2.0 预留 |
| **2.3 清洗标准化** | T2.2 |
| **2.4 动作+延迟红线** | T2.4(>10s drop) + M3 ★G03(4 动作路由) |
| **2.5 前台展示** | T2.9 策略广场 + T2.10 策略详情 |
| **2.6 两级数据池** | T2.5 待选池 + T2.6 已添加池 |
| **2.7 带单员门槛** | T2.6 ★G04(55%/30%/30d) |
| **2.8 前端筛选排序** | T2.9 |
| **2.9 异常隔离+占位** | T2.11 缓存兜底 |
| **2.10 反爬(间隔+代理池)** | T2.1 ★反爬(3-8s+代理池) |
| **2.11 画像异常标注** | T2.7 告警 + T2.11 "数据更新于昨日" |
| **3.1 注册/验证码/邀请绑定** | T1.2 + T1.4 |
| **3.2 选所+身份A/B** | T1.4 ★G06(PlatformPool 自动识别) |
| **3.3 多所 API 绑定(拒提现)** | T1.5 + T1.6 |
| **3.4 跨所匹配校验** | T3.2 + M3 §4.4 |
| **4.1 跟单配置(逐仓/全仓)** | T3.2 ★G07(margin_mode) |
| **4.2 执行规则(10s/5s/失败归因)** | T3.6 + T3.8(8 类) |
| **4.3 USDT 4 步换算** | T3.4 ★G08(合约级 ContractSpec) |
| **4.4 独立机器人(虚拟账本)** | T3.3 + T3.9 |
| **4.5 风控校验** | T3.5(5 条规则) |
| **5.1-5.7 订阅收费** | T4.1/T4.2(套餐+限购)/T4.3/T4.4(三链核实)/★G09/T4.8(RPC)/★G10(过期拦截=M3) |
| **6.1-6.6 邀请奖励** | T4.5(10% + 24h + ★G11 48h)/T4.9(刷单检测)/T5.7(关系管理) |
| **7.1-7.6 奖励余额** | T4.1(状态机)/T4.5(流水账)/T4.6(提现关联)/T4.11(★G12 5 字段) |
| **8.1-8.4 提现** | T4.6(★G13 10U 门槛)/T4.7(审核)/T4.12(表单)/T5.9(后台审核) |
| **9.1-9.2 后台 10 模块** | T5.1-T5.11 + T5.12(RBAC) |
| **10.1 首页(4卡/隐私/新手)** | T5.13(★G22 眼睛) + T5.14(★G23 新手引导) |
| **10.2 策略广场/我的跟单** | M2 T2.9/T2.10 + M3 T3.9 |
| **10.3 个人中心(API/邀请/奖励/提现/安全)** | T1.8 + M4 T4.10-T4.12 + M5 T5.15-T5.18 |

> 核对修订记录：① M5 原误补 T5.15-T5.17(策略广场/详情/我的跟单)与 M2/M3 重复，已删除；② T2.1 补★反爬代理池；③ G21 落地位置更正为 M2 T2.10/T2.11。

---

## 13. V1.0 交付清单（DoD：Definition of Done）

进入 M6 上线检查时必须全部满足：

- [ ] **功能**：邮箱注册 / 验证码 / 选所 / 绑邀请 / ★G06:PlatformPool 自动识别主号下级 / 绑 Gate API（拒提现） / 策略广场浏览 / ★G04:带单员门槛校验(胜率≥55%/回撤≤30%/天数≥30) / ★G05:TraderProfile 4 段 ROI(7d/30d/90d/累计) / 我的跟单机器人 CRUD（★G07:含逐仓/全仓 margin_mode）/ ★G03:4 种信号动作(开/加/减/平) / ★G08:ContractSpec 合约级精度 / ★G10:过期拦截开仓/加仓但放行平仓/减仓 / 5U 试用限购 1 次 / 19.9U 正式 / ★G09:TRC-20+BEP-20+ERC-20 三链支付自动校验 / ★G11:24h/48h 奖励核实(高危延长) / ★G13:10U 起提(统一) / 1U 手续费 / ★G12:奖励余额 5 字段(含冻结) / 人工提现审核 / 后台 10 模块 / 强制风险揭示 / 邀请刷单检测
- [ ] **安全**：API key AES-256-GCM 加密；拒绝提现权限；后台与前台完全隔离；管理员操作全部留痕；TOTP 可后置但 RBAC 已生效
- [ ] **可观测**：6 个核心指标 + Grafana 看板；trace_id 端到端串联
- [ ] **测试**：USDT 4 步换算（★G08:合约级精度） / 5 条风控规则（★G03:含 action 路由 + ★G10:过期拦截） / 8 类失败归因 单测覆盖；★G04:门槛校验(force/force_skip) / ★G11:48h 延长核实 / ★G12:5 字段余额快照 各 2 用例；至少 1 个端到端集成测试
- [ ] **合规**：法务评估通过；不抽水/不返佣；风险揭示文案就绪
- [ ] **性能**：100 并发用户 / p95 < 500ms；压测报告存档
- [ ] **部署**：Docker Compose 一键起；PG/Redis 备份策略；密钥轮换演练通过
- [ ] **文档**：README + API 文档 + 部署文档 + 运维 Runbook
- [ ] **需求覆盖度**：需求 1-10 章 62 个功能点全部实现；★G21：策略详情画像兜底(is_stale/placeholder) / ★G22：首页金额隐藏/显示 / ★G23：新手三步引导 / ★G26：信号源运维看板字段(source_mode/子账户/WS 状态) 就绪

---

## 14. V1 之后的路线（占位，不含时间）

| 阶段 | 范围 | 复用 signal-aggregator 方式 |
|---|---|---|
| V1.1 | OKX + Bybit | 接入 `AbstractExchangeAdapter` |
| V1.2 | Bitget + Binance | 复用注册表 + 5×3 抽象 |
| V2.0 | 模式 B 小号 WS + ERC-20 提现 + 地址白名单 | 引入 `MiniAccountAdapter`；引入 KMS |
| V2.x | 信号评分 / Trader 排行榜 / 回测 / 灰度 / 多语言 | 在抽象层加 `signal-scorer` 模块 |

---

## 15. 文档管理

- 本计划文档路径：`docs/2026-08-12-signal-saas-v1-development-plan.md`
- 关联基线：`docs/2026-08-12-signal-saas-platform-design.md`
- 每次里程碑结束需回写：实际工期 vs 估算 + 偏差原因 + 新发现的风险
- 任何模块超出原计划范围（新增模块/接口）必须先回写本计划与设计蓝本再实现

---

## 字数与结构摘要

- **约 5,800 中文字**
- **6 个里程碑（M0-M6）+ 1 个 V1 DoD + 1 个 V1+ 路线**
- **70+ 任务**，平均 1-3 天工作量
- **15 章节**，含依赖图 + 横切关注点 + 关键文件清单 + 风险与差异化对照
- 所有接口签名、状态机、SQL 字段与设计蓝本严格一致；不引入新契约

---

> 本计划完成于 2026-08-12；任何字段、任务、验收门的二次变更必须先回写本文档再实施。