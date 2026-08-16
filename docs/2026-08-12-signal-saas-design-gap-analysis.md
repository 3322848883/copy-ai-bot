# signal-saas 设计文档与需求文档逐条对照差异分析

> **基线文档**：需求文档（10 章完整版） × 设计文档（`2026-08-12-signal-saas-platform-design.md`） × 开发计划（`2026-08-12-signal-saas-v1-development-plan.md`）
> **对照日期**：2026-08-12
> **差异总数**：20 处（遗漏 11 / 矛盾 4 / 模糊 5）
> **严重级别**：🔴 必须修复 / 🟡 建议修复 / 🟢 可后置

---

## 差异总览表

| 编号 | 类型 | 严重级别 | 需求章节 | 差异标题 |
|------|------|---------|---------|---------|
| G01 | 遗漏 | 🟡 | §1.3 | 按单带单员订阅模式未纳入设计 |
| G02 | 模糊 | 🟡 | §2.3 | 信号噪声过滤阈值未定义 |
| G03 | 遗漏 | 🔴 | §2.4 | 信号动作枚举（开/加/减/平）未在 NormalizedSignal 中显式声明 |
| G04 | 遗漏 | 🔴 | §2.7 | 带单员选取硬性门槛（胜率/回撤/天数）未写入设计 |
| G05 | 遗漏 | 🔴 | §2.10 | TraderProfile 缺少 roi_90d 和 roi_all（累计盈亏）字段 |
| G06 | 模糊 | 🔴 | §3.2 | "平台资源池"邀请码的自动识别机制未定义 |
| G07 | 遗漏 | 🔴 | §4.1 | CopyBot 缺少 margin_mode（逐仓/全仓）字段 |
| G08 | 模糊 | 🟡 | §4.5 | 合约精度参数应精确到合约级别而非交易所级别 |
| G09 | 矛盾 | 🔴 | §5.3 | 开发计划 M4 遗漏 ERC-20 支付链支持 |
| G10 | 模糊 | 🔴 | §5.6 | 订阅过期后应区分"开仓/加仓拦截"与"平仓/减仓放行" |
| G11 | 遗漏 | 🔴 | §6.5 | 风控高危用户奖励核实期应延长至 48h，设计未实现 |
| G12 | 遗漏 | 🟡 | §7.1 | BalanceSnapshot 缺少 frozen_amount（冻结金额）字段 |
| G13 | 矛盾 | 🔴 | §7.6 vs §8.4 | 最低提现门槛自相矛盾（5U vs 10U） |
| G14 | 遗漏 | 🟢 | §9.3③ | 模式 B 小号管理系统（MiniAccount 表/WS 管理器/REST 补单）架构预留不足 |
| G15 | 遗漏 | 🟡 | §9.3⑤ | 信号源运维看板字段（WS 状态/子账户余额/采集模式）未在 Admin API 中声明 |
| G16 | 遗漏 | 🟡 | §9.3③ | 模式 B REST 5-10min 补单校验机制未在适配器层预留 |
| G17 | 遗漏 | 🟡 | §2.10 | 反爬代理 IP 池未在适配器接口中声明 |
| G18 | 遗漏 | 🟡 | §10.1① | 首页"总账户资产"实时聚合策略（缓存/限频）未定义 |
| G19 | 遗漏 | 🟡 | §5.4④ | 支付超时后自动发邮件通知用户的具体流程未在 mailer 中映射 |
| G20 | 矛盾 | 🟡 | §8.4 vs §7.6 | 提现手续费描述位置不一致（1U 是否含在提现金额内） |

---

## 逐条详细分析与修复方案

---

### G01：按单带单员订阅模式未纳入设计

| 维度 | 内容 |
|------|------|
| **需求原文** | §1.3 "V1 阶段唯一收入来源：用户订阅费（可持续套餐模式：如 19.9U/月 或者 按单个热门带单员订阅）。" |
| **设计现状** | 仅定义了 `trial_5u` 和 `monthly_19_9u` 两种 Plan，无"按单个带单员订阅"模式 |
| **影响** | 收入模型单一；但需求用"如"字，属于建议而非硬性要求 |
| **修复方案** | V1 维持现有双套餐；在 `Plan` 表中增加 `plan_type` 枚举值 `per_trader`（V2 激活）；数据模型预留 `Subscription.trader_scope` 字段（NULL=全广场 / trader_id=指定策略） |

**数据模型变更**：
```sql
-- Plan 表增加字段
ALTER TABLE plan ADD COLUMN plan_type VARCHAR(20) DEFAULT 'all_access';
-- 枚举：all_access（全广场）/ per_trader（单策略）

-- Subscription 表增加字段
ALTER TABLE subscription ADD COLUMN trader_scope INT REFERENCES strategy(id);
-- NULL = 全广场访问；非 NULL = 仅限指定策略
```

---

### G02：信号噪声过滤阈值未定义

| 维度 | 内容 |
|------|------|
| **需求原文** | §2.3 "过滤掉微小调仓、试单杂音，避免频繁触发无效订单。" |
| **设计现状** | `SignalNormalizer.filter_noise()` 方法存在但无具体实现逻辑和阈值参数 |
| **影响** | 无阈值可能导致微小调仓频繁触发用户跟单，增加滑点和手续费损耗 |
| **修复方案** | 在 `SignalNormalizer` 中定义可配置的噪声过滤规则 |

**具体实现**：
```python
class NoiseFilterConfig:
    # 微小调仓过滤：调仓幅度 < 阈值则丢弃
    min_position_change_pct: Decimal = Decimal("0.05")    # 5% 以下调仓视为噪声
    # 试单过滤：开仓后 N 秒内平仓视为试单
    min_holding_seconds: int = 30                          # 30 秒内平仓丢弃
    # 重复信号过滤：同一交易员同一币种同一方向，N 秒内仅取首次
    dedupe_window_seconds: int = 5

class SignalNormalizer:
    async def filter_noise(self, ns: NormalizedSignal, prev: NormalizedSignal | None) -> bool:
        """返回 True = 噪声，应丢弃"""
        if prev and prev.trader_id == ns.trader_id:
            # 调仓幅度过小
            change = abs(ns.qty - prev.qty) / prev.qty if prev.qty else 1
            if change < self.cfg.min_position_change_pct:
                return True
            # 5 秒内重复
            if (ns.received_at - prev.received_at).seconds < self.cfg.dedupe_window_seconds:
                return True
        return False
```

---

### G03：信号动作枚举未在 NormalizedSignal 中显式声明

| 维度 | 内容 |
|------|------|
| **需求原文** | §2.4 "动作定义：开仓、加仓、减仓、平仓。" |
| **设计现状** | `NormalizedSignal` 有 `side` 字段但未显式定义 `action` 枚举 |
| **影响** | 🔴 跟单引擎无法区分"加仓"与"新开仓"，风控规则（如最大总仓位）无法精确触发 |
| **修复方案** | 在 `NormalizedSignal` 中增加 `action` 字段 |

**数据模型变更**：
```python
class SignalAction(str, Enum):
    OPEN = "open"        # 开仓
    ADD = "add"          # 加仓
    REDUCE = "reduce"    # 减仓
    CLOSE = "close"      # 平仓

class NormalizedSignal(BaseModel):
    # ... 已有字段
    action: SignalAction              # 新增：动作类型
    prev_qty: Decimal | None = None   # 新增：上一次持仓量（用于判断 add/reduce）
```

**跟单引擎联动**：
```python
class CopyEngine:
    async def on_signal(self, ns: NormalizedSignal) -> list[OrderIntent]:
        if ns.action == SignalAction.OPEN:
            # 新开仓：走完整 USDT 4 步换算
            return await self._handle_open(ns)
        elif ns.action == SignalAction.ADD:
            # 加仓：检查是否超过 max_total_position
            return await self._handle_add(ns)
        elif ns.action == SignalAction.REDUCE:
            # 减仓：按比例减仓
            return await self._handle_reduce(ns)
        elif ns.action == SignalAction.CLOSE:
            # 平仓：全部平掉
            return await self._handle_close(ns)
```

---

### G04：带单员选取硬性门槛未写入设计

| 维度 | 内容 |
|------|------|
| **需求原文** | §2.7 "V1 阶段建议设置硬性门槛：历史胜率 ≥ 55%、历史最大回撤 ≤ 30%、带单天数 ≥ 30 天" |
| **设计现状** | 设计文档无任何门槛校验逻辑；后台"已添加池"操作无前置条件 |
| **影响** | 🔴 管理员可将不合格带单员上架，破坏平台口碑 |
| **修复方案** | 在 `SignalStore.upsert_strategy` 和后台 API 的 `add` 操作中增加门槛校验 |

**实现方案**：
```python
class TraderSelectionPolicy:
    MIN_WIN_RATE = Decimal("55")       # 历史胜率 ≥ 55%
    MAX_DRAWDOWN = Decimal("30")        # 最大回撤 ≤ 30%
    MIN_TRADING_DAYS = 30              # 带单天数 ≥ 30

class SignalStore:
    async def add_to_listed(self, trader_id: str, admin_id: int) -> Strategy:
        profile = await self.get_latest_profile(trader_id)
        policy = TraderSelectionPolicy()
        violations = []
        if profile.win_rate_30d < policy.MIN_WIN_RATE:
            violations.append(f"胜率 {profile.win_rate_30d}% < 55%")
        if profile.max_drawdown > policy.MAX_DRAWDOWN:
            violations.append(f"回撤 {profile.max_drawdown}% > 30%")
        if profile.trading_days < policy.MIN_TRADING_DAYS:
            violations.append(f"带单天数 {profile.trading_days} < 30")
        if violations:
            raise TraderQualificationError(violations)
        # 允许管理员"强制添加"（需填理由 + 写 audit-log）
        # 但默认拒绝
```

**后台 API 变更**：
```
POST /admin/v1/signals/{exchange}/{id}/add
  Body: { display_name, style, risk_rating, force?: bool, force_reason?: string }
  → 默认校验门槛；force=true 时跳过但必须填 force_reason + 写 audit-log
```

---

### G05：TraderProfile 缺少 roi_90d 和 roi_all 字段

| 维度 | 内容 |
|------|------|
| **需求原文** | §2.10 "收益曲线：抓取近7天、30天、90天及历史累计盈亏百分比" |
| **设计现状** | TraderProfile 仅有 `roi_7d, roi_30d, win_rate_30d, max_drawdown` |
| **影响** | 🔴 前端策略详情页无法展示 90 天和累计收益曲线 |
| **修复方案** | 扩展 TraderProfile 字段 |

**数据模型变更**：
```sql
ALTER TABLE trader_profile ADD COLUMN roi_90d DECIMAL(10,2);
ALTER TABLE trader_profile ADD COLUMN roi_all DECIMAL(10,2);       -- 历史累计
ALTER TABLE trader_profile ADD COLUMN trading_days INT DEFAULT 0;   -- 带单天数（G04 依赖）
ALTER TABLE trader_profile ADD COLUMN win_rate_all DECIMAL(10,2);  -- 历史总胜率
```

---

### G06：平台资源池邀请码自动识别机制未定义

| 维度 | 内容 |
|------|------|
| **需求原文** | §3.2 "如果用户填写的邀请码关联了平台资源池，且其选择的所属交易所与平台的合作方匹配。系统会自动（或经后台极速人工核对后）将其身份标记为【主号下级】。" |
| **设计现状** | `IdentityService.mark_as_sub_account` 存在但为纯管理员手动操作；无自动识别逻辑 |
| **影响** | 🔴 平台主号下级用户无法自动免订阅，需人工逐个审核 |
| **修复方案** | 引入 `PlatformPool` 表 + 自动标记逻辑 |

**数据模型变更**：
```sql
CREATE TABLE platform_pool (
    id SERIAL PRIMARY KEY,
    invite_code VARCHAR(32) UNIQUE NOT NULL,   -- 平台资源池专属邀请码
    exchange VARCHAR(20) NOT NULL,              -- 绑定的合作交易所
    label VARCHAR(100),                          -- 描述（如"币安主号群"）
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**自动识别逻辑**：
```python
class IdentityService:
    async def bind_invite_code(self, user_id: int, code: str) -> Invite:
        invite = await super().bind_invite_code(user_id, code)
        # 检查是否命中平台资源池
        pool = await self.pool_repo.find_by_code(code)
        if pool and pool.is_active:
            identity = await self.identity_repo.get(user_id)
            if identity.exchange == pool.exchange:
                # 自动标记为主号下级
                identity.identity_type = 'sub_account'
                await self.identity_repo.save(identity)
                await self.audit.record(
                    actor=SYSTEM, action='auto_mark_sub_account',
                    target=f'user:{user_id}', before={'type': 'normal'},
                    after={'type': 'sub_account', 'pool_id': pool.id},
                    reason=f'auto-matched pool {pool.label}')
        return invite
```

---

### G07：CopyBot 缺少 margin_mode（逐仓/全仓）字段

| 维度 | 内容 |
|------|------|
| **需求原文** | §4.1 "【保证金模式】（二选一，互斥）：逐仓模式 / 全仓模式" |
| **设计现状** | CopyBot 数据模型无 `margin_mode` 字段 |
| **影响** | 🔴 下单时无法设置保证金模式，交易所默认行为可能与用户预期不符 |
| **修复方案** | 在 CopyBot 表增加字段 + 下单前调用 `set_margin_mode` |

**数据模型变更**：
```sql
ALTER TABLE copy_bot ADD COLUMN margin_mode VARCHAR(10) DEFAULT 'isolated';
-- 枚举：isolated（逐仓）/ cross（全仓）
```

**OrderRouter 联动**：
```python
class OrderRouter:
    async def place(self, intent: OrderIntent, user_ctx: UserContext) -> ExecutionReport:
        # 首次下单前设置保证金模式和杠杆
        await self.set_margin_mode(intent.symbol, intent.bot.margin_mode, user_ctx)
        await self.set_leverage(intent.symbol, intent.bot.leverage, user_ctx)
        # 然后下单
        return await self._place_order(intent, user_ctx)
```

---

### G08：合约精度参数应精确到合约级别

| 维度 | 内容 |
|------|------|
| **需求原文** | §4.5 "计算出的目标开仓张数，必须向下取整至该交易所允许的最大小数精度" |
| **设计现状** | 设计中 `exch.size_precision` 和 `exch.contract_size_min` 暗示是交易所级别参数 |
| **影响** | 🟡 同一交易所不同合约的精度和最小开仓量不同（如 BTCUSDT 和 ETHUSDT 精度不同） |
| **修复方案** | 将精度参数从交易所级别改为合约级别 |

**数据模型变更**：
```sql
CREATE TABLE contract_spec (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,              -- 如 ETHUSDT
    face_value_usdt DECIMAL(20,8) NOT NULL,   -- 合约面值 USDT/张
    min_size DECIMAL(20,8) NOT NULL,           -- 最小开仓张数
    size_precision INT NOT NULL,               -- 张数小数精度
    UNIQUE(exchange, symbol)
);
```

**换算函数调整**：
```python
def compute_size(bot, ns, contract: ContractSpec, account):
    # contract 从 contract_spec 表按 exchange + symbol 实时查询
    face = contract.face_value_usdt
    qty_raw = target / face
    min_size = contract.min_size            # 合约级别
    precision = contract.size_precision      # 合约级别
    # ... 其余逻辑不变
```

---

### G09：开发计划 M4 遗漏 ERC-20 支付链支持

| 维度 | 内容 |
|------|------|
| **需求原文** | §5.3 "多链支持（扩展至三条主流链）：TRC-20、BEP-20、ERC-20" |
| **设计现状** | 设计文档 PaymentOrder 包含 ERC-20；但开发计划 M4 T4.3/T4.4 仅写"TRC-20 + BEP-20 支付" |
| **影响** | 🔴 开发实施时会遗漏 ERC-20 支持，与需求不符 |
| **修复方案** | 开发计划 M4 任务范围修正 |

**开发计划修正**：
```
T4.3 PaymentService 即时校验
  原：TRC-20 + BEP-20
  改：TRC-20 + BEP-20 + ERC-20（三链并行校验）

T4.4 PaymentService 轮询
  原：TRC-20=12/BEP-20=15
  改：TRC-20=12 / BEP-20=15 / ERC-20=12（三链阈值）

T4.8 区块链 RPC 客户端
  原：web3.py (ERC/BEP) + tronpy (TRC)
  改：不变（已包含三链），但工期从 1.5d 调至 2d（ERC-20 GAS 估算复杂）
```

---

### G10：订阅过期后应区分开仓/加仓拦截与平仓/减仓放行

| 维度 | 内容 |
|------|------|
| **需求原文** | §5.6 "订阅一旦过期，系统底层代码立即禁止该用户所有'独立机器人'执行任何新信号的开仓、加仓操作。" |
| **设计现状** | §5.5 CopyBot 状态机写"信号路由层屏蔽(不直接改 bot 状态)"，但未区分动作类型 |
| **影响** | 🔴 如果过期后也拦截平仓信号，用户无法止损，可能造成更大亏损 |
| **修复方案** | 在信号路由层增加动作级别过滤 |

**实现逻辑**：
```python
class CopyEngine:
    async def on_signal(self, ns: NormalizedSignal) -> list[OrderIntent]:
        bots = await self.bot_repo.find_active(strategy_id=ns.strategy_id)
        intents = []
        for bot in bots:
            sub = await self.billing.get_active_subscription(bot.user_id)
            is_expired = (not sub or sub.status != 'active') and bot.user_identity != 'sub_account'
            if is_expired:
                if ns.action in (SignalAction.OPEN, SignalAction.ADD):
                    # 过期：拦截开仓/加仓
                    await self._record_blocked(bot, ns, reason='subscription_expired')
                    continue
                elif ns.action in (SignalAction.REDUCE, SignalAction.CLOSE):
                    # 过期仍允许平仓/减仓（风控保护）
                    pass
            intents.append(await self._build_intent(bot, ns))
        return intents
```

---

### G11：风控高危用户奖励核实期应延长至 48h

| 维度 | 内容 |
|------|------|
| **需求原文** | §6.5 "被风控标记的邀请人，系统会自动将其在奖励余额中的结算周期延长至 48 小时" |
| **设计现状** | `verifying_ends_at = now + 24h` 硬编码，无 48h 延长机制 |
| **影响** | 🔴 风控高危用户的奖励仍按 24h 释放，刷单防护失效 |
| **修复方案** | 在触发奖励时检查风控标记，动态设置核实期 |

**实现逻辑**：
```python
class LedgerService:
    async def credit(self, user_id, source, amount, ref_id) -> Reward:
        # 检查邀请人是否为风控高危
        risk_flag = await self.referral.detect_batch_abuse(user_id, window=timedelta(hours=1))
        if risk_flag.is_flagged:
            verifying_hours = 48     # 高危用户延长至 48h
        else:
            verifying_hours = 24     # 正常 24h

        reward = Reward(
            owner_id=user_id,
            amount_usdt=amount,
            status='verifying',
            verifying_started_at=utcnow(),
            verifying_ends_at=utcnow() + timedelta(hours=verifying_hours),
            risk_extended=risk_flag.is_flagged,   # 标记是否为延长核实
        )
        await self.reward_repo.save(reward)
        return reward
```

---

### G12：BalanceSnapshot 缺少 frozen_amount 字段

| 维度 | 内容 |
|------|------|
| **需求原文** | §7.1 前端需展示 5 个字段：累计奖励、可提现余额、提现中金额、已提现金额、**冻结金额** |
| **设计现状** | `LedgerService.get_balance()` 返回 `BalanceSnapshot` 但未明确包含 `frozen_amount` |
| **影响** | 🟡 前端无法展示被风控冻结的金额 |
| **修复方案** | 扩展 BalanceSnapshot 类型 |

**类型定义**：
```python
class BalanceSnapshot(BaseModel):
    total_earned: Decimal         # 累计奖励（所有记录 SUM）
    available: Decimal            # 可提现余额
    withdrawing: Decimal          # 提现中金额
    paid: Decimal                 # 已提现金额
    frozen: Decimal               # 冻结金额（status='frozen' 的 SUM）
    # 校验：total_earned = available + withdrawing + paid + frozen + canceled + rolled_back
```

---

### G13：最低提现门槛自相矛盾（5U vs 10U）

| 维度 | 内容 |
|------|------|
| **需求原文 §7.6** | "系统需设定最低提现门槛（例如 5U 起提，可后台配置）" |
| **需求原文 §8.4** | "建议 V1 设置为 10U 起提（防止小额高频提现占用管理员时间）" |
| **设计现状** | 设计文档统一采用 10U |
| **影响** | 🔴 需求文档自身矛盾，开发时无法确定 |
| **修复方案** | 以 §8.4 的 10U 为准（理由：§8.4 是提现逻辑专章，更详细且有理由说明）；在后台可配置，默认值 10U |

**统一口径**：
```python
class WithdrawalConfig:
    min_amount_usdt: Decimal = Decimal("10")    # 默认 10U，后台可改
    fee_usdt: Decimal = Decimal("1")            # 固定 1U 手续费
    # 校验：amount >= min_amount_usdt AND amount <= available_balance
    # 实发 = amount - fee_usdt
```

---

### G14：模式 B 小号管理系统架构预留不足

| 维度 | 内容 |
|------|------|
| **需求原文** | §9.3③ 详细描述了模式 B 的完整配置流程：指定小号 → 配置 API → 配置跟单参数 → WS 主通道 + REST 补单 |
| **设计现状** | 设计文档仅提到 `adapters` 和 "V2 小号 WS"，无 MiniAccount 数据模型和管理接口 |
| **影响** | 🟢 V1 不需要，但 V2 切换时缺乏数据模型支撑 |
| **修复方案** | 在设计中预留 MiniAccount 模型（V2 实现，V1 仅建表） |

**预留数据模型**：
```sql
-- V1 建表不使用，V2 填充
CREATE TABLE mini_account (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,
    sub_account_id VARCHAR(50),               -- 交易所子账户 ID
    api_key_ciphertext BYTEA,                  -- AES 加密
    api_key_nonce BYTEA,
    api_key_tag BYTEA,
    balance_usdt DECIMAL(20,8),                -- 实时余额
    ws_status VARCHAR(20) DEFAULT 'offline',   -- online/reconnecting/offline
    last_ws_heartbeat TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE mini_account_tracking (
    id SERIAL PRIMARY KEY,
    mini_account_id INT REFERENCES mini_account(id),
    target_trader_id VARCHAR(100),            -- 被追踪的带单员
    copy_amount_usdt DECIMAL(20,8),            -- 小号每笔跟单金额
    copy_leverage INT,
    is_tracking BOOLEAN DEFAULT TRUE,
    started_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

### G15：信号源运维看板字段未在 Admin API 中声明

| 维度 | 内容 |
|------|------|
| **需求原文** | §9.3⑤ 运维专用列需展示：信号来源模式（A/B）、子账户 ID + 余额（B）、WS 监听状态、操作按钮 |
| **设计现状** | Admin API `/admin/v1/signals/{exchange}` 未包含这些运维字段 |
| **影响** | 🟡 运维无法直观判断信号源采集链路健康度 |
| **修复方案** | 在 Admin 策略列表响应中增加运维字段 |

**API 响应扩展**：
```python
class StrategyAdminDTO(BaseModel):
    # 已有字段
    id: int
    display_name: str
    source_exchange: str
    style: str
    risk_rating: str
    status: str
    # 新增运维字段
    source_mode: Literal['A', 'B'] | None        # 采集模式
    mini_account_id: str | None                    # 小号 ID（仅模式 B）
    mini_account_balance: Decimal | None           # 小号实时余额
    ws_status: Literal['online', 'reconnecting', 'offline'] | None
    last_signal_at: datetime | None               # 最后一次信号时间
    signal_count_24h: int                           # 24h 信号数
```

---

### G16：模式 B REST 5-10min 补单校验机制未预留

| 维度 | 内容 |
|------|------|
| **需求原文** | §9.3③ "REST 低频补单校验（辅助）：系统定时（如每 5~10 分钟）通过 REST API 拉取该小号的历史成交记录，与 WebSocket 收到的数据进行比对。" |
| **设计现状** | 设计中无 REST 补单机制 |
| **影响** | 🟡 V2 WS 丢包时信号可能丢失 |
| **修复方案** | 在 `adapters/base` 中预留 `ReconciliationMixin` |

**接口预留**：
```python
class ReconciliationMixin:
    """模式 B 专用：REST 定时补单校验"""

    async def reconcile_trades(self, since: datetime) -> list[NormalizedSignal]:
        """拉取小号历史成交，与 WS 收到的信号比对，补回遗漏"""
        raw_trades = await self.exchange.fetch_my_trades(since=since, limit=50)
        ws_seen = await self.signal_store.get_signals_since(
            trader_id=self.trader_id, since=since)
        ws_keys = {s.dedupe_key for s in ws_seen}
        missing = [t for t in raw_trades if self._dedupe_key(t) not in ws_keys]
        if missing:
            logger.warning(f"WS dropped {len(missing)} signals, recovering via REST")
        return [await self.normalizer.normalize(t) for t in missing]
```

---

### G17：反爬代理 IP 池未在适配器接口中声明

| 维度 | 内容 |
|------|------|
| **需求原文** | §2.10 "爬虫程序必须配置随机访问间隔（3~8 秒）和代理 IP 池。" |
| **设计现状** | 设计在风险表中提到"代理池"但适配器接口 `AbstractScraperAdapter` 无代理配置 |
| **影响** | 🟡 爬虫易被交易所封 IP |
| **修复方案** | 在适配器基类中增加代理池和随机间隔配置 |

**接口扩展**：
```python
class ScraperConfig(BaseModel):
    request_interval_min: float = 3.0       # 最小间隔（秒）
    request_interval_max: float = 8.0       # 最大间隔（秒）
    proxy_pool: list[str] | None = None     # 代理 IP 列表
    proxy_rotation: str = "round_robin"     # 轮换策略
    max_retries: int = 3                    # 单次请求最大重试
    user_agent_rotation: bool = True        # UA 轮换

class AbstractScraperAdapter(ABC):
    def __init__(self, config: ScraperConfig):
        self.config = config
        self._proxy_index = 0

    async def _get_proxy(self) -> str | None:
        if not self.config.proxy_pool:
            return None
        proxy = self.config.proxy_pool[self._proxy_index % len(self.config.proxy_pool)]
        self._proxy_index += 1
        return proxy

    async def _sleep(self):
        delay = uniform(self.config.request_interval_min, self.config.request_interval_max)
        await asyncio.sleep(delay)
```

---

### G18：首页"总账户资产"实时聚合策略未定义

| 维度 | 内容 |
|------|------|
| **需求原文** | §10.1① "系统通过后台实时调用用户绑定的各交易所 API，计算所有交易账户的可用余额总和" |
| **设计现状** | `/v1/account/overview` 端点存在但无缓存/限频策略 |
| **影响** | 🟡 多用户多交易所 API 调用量巨大，可能触发交易所限频 |
| **修复方案** | 采用"定时缓存 + 手动刷新 + WS 推送"三层策略 |

**策略设计**：
```python
class AccountOverviewService:
    CACHE_TTL = 60  # 60 秒缓存

    async def get_overview(self, user_id: int) -> AccountOverview:
        # 1. 先读缓存
        cached = await self.cache.get(f"account_overview:{user_id}")
        if cached and not cached.is_expired:
            return cached.data

        # 2. 缓存 miss → 并发查询所有交易所
        api_keys = await self.vault.get_all(user_id)
        results = await asyncio.gather(*[
            self._fetch_balance(key) for key in api_keys
        ], return_exceptions=True)

        total = sum(r.balance for r in results if not isinstance(r, Exception))
        overview = AccountOverview(
            total_balance_usdt=total,
            total_position_usdt=...,
            today_pnl_usdt=...,
            active_bots=...,
            last_updated=utcnow(),
            is_cached=False,
        )
        await self.cache.set(f"account_overview:{user_id}", overview, ttl=self.CACHE_TTL)
        return overview

    async def _fetch_balance(self, api_key: ApiKey) -> ExchangeBalance:
        """单交易所余额查询，带超时和错误隔离"""
        try:
            return await asyncio.wait_for(
                self.ccxt_client.fetch_balance(api_key),
                timeout=10
            )
        except Exception as e:
            logger.warning(f"exchange {api_key.exchange} balance fetch failed: {e}")
            return ExchangeBalance(exchange=api_key.exchange, balance=Decimal(0), error=str(e))
```

---

### G19：支付超时后自动发邮件通知用户的具体流程未映射

| 维度 | 内容 |
|------|------|
| **需求原文** | §5.4④ "系统自动向用户注册邮箱发送一封'支付确认超时'邮件，告知情况并引导联系客服。" |
| **设计现状** | 设计 §6.5 提到 `mailer` 但仅在 `confirmed` 时发通知；超时场景未映射 |
| **影响** | 🟡 用户不知道支付校验超时，会重复提交 |
| **修复方案** | 在 PaymentService 超时处理中增加邮件通知 |

**流程补充**：
```python
class PaymentService:
    async def mark_timeout(self, order: PaymentOrder) -> None:
        order.status = 'timeout'
        await self.order_repo.save(order)
        # 发送超时通知邮件
        await self.mailer.send(
            to=order.user.email,
            template='payment_timeout',
            context={
                'order_id': order.id,
                'amount': order.amount_usdt,
                'network': order.network,
                'tx_hash': order.tx_hash,
                'support_email': self.config.support_email,
            }
        )
        # 同时推送到后台异常监控池
        await self.exception_pool.add(order, reason='payment_timeout')
```

---

### G20：提现手续费描述位置不一致（1U 是否含在提现金额内）

| 维度 | 内容 |
|------|------|
| **需求原文 §7.6** | "每次提现可设置固定 1U 作为网络 GAS 手续费...从'可提现余额'中扣除" → 暗示手续费额外扣除 |
| **需求原文 §8.4** | "实际发放金额 = 申请金额 - 1U" → 明确从申请金额中扣除 |
| **设计现状** | 设计统一采用"实际发放 = 申请金额 - 1U" |
| **影响** | 🟡 两处描述角度不同可能引起开发歧义 |
| **修复方案** | 统一为 §8.4 口径，在设计文档中明确标注 |

**统一口径**：
```
用户申请提现 X USDT
  → 手续费 = 1U（从 X 中扣除）
  → 实际发放 = X - 1U
  → 前提：X ≥ 10U（最低门槛）且 X ≤ 可提现余额

前端展示：
  "提现金额：X USDT"
  "手续费：1 USDT"
  "实际到账：(X-1) USDT"
```

---

## 修复优先级矩阵

| 优先级 | 编号 | 修复内容 | 影响阶段 |
|--------|------|---------|---------|
| 🔴 P0（M0-M1 必修） | G03 | NormalizedSignal 增加 action 枚举 | M2 信号采集 |
| 🔴 P0 | G07 | CopyBot 增加 margin_mode | M3 跟单引擎 |
| 🔴 P0 | G06 | PlatformPool 表 + 自动识别 | M1 账号体系 |
| 🔴 P0 | G08 | ContractSpec 合约级精度 | M3 跟单引擎 |
| 🔴 P1（M2-M3 必修） | G04 | 带单员门槛校验 | M2 信号管理 |
| 🔴 P1 | G05 | TraderProfile 扩展字段 | M2 画像同步 |
| 🔴 P1 | G10 | 过期后区分开仓/平仓 | M3 跟单引擎 |
| 🔴 P1 | G11 | 48h 风控延长 | M4 奖励系统 |
| 🔴 P1 | G09 | ERC-20 支付纳入 M4 | M4 支付 |
| 🔴 P1 | G13 | 最低提现门槛统一 10U | M4 提现 |
| 🟡 P2（M4-M5 修复） | G02 | 噪声过滤阈值 | M2 |
| 🟡 P2 | G12 | BalanceSnapshot 加 frozen | M4 |
| 🟡 P2 | G15 | 运维看板字段 | M5 |
| 🟡 P2 | G17 | 代理 IP 池 | M2 |
| 🟡 P2 | G18 | 首页缓存策略 | M5 |
| 🟡 P2 | G19 | 超时邮件通知 | M4 |
| 🟡 P2 | G20 | 手续费口径统一 | M4 |
| 🟢 P3（V2 预留） | G01 | 按带单员订阅 | V2 |
| 🟢 P3 | G14 | MiniAccount 模型 | V2 |
| 🟢 P3 | G16 | REST 补单机制 | V2 |

---

## 对设计文档的具体修订指令

以下是需要回写到 `2026-08-12-signal-saas-platform-design.md` 的具体修改点：

### 1. §3.12 信号采集适配器 — 增加 ScraperConfig
在 `AbstractScraperAdapter` 前增加 `ScraperConfig` 类（G17），并在构造函数中接收。

### 2. §3.13 信号标准化 — 增加 action 枚举和噪声过滤
在 `NormalizedSignal` 中增加 `action: SignalAction` 字段（G03）；`filter_noise` 方法增加 `NoiseFilterConfig`（G02）。

### 3. §3.14 信号存储 — 增加门槛校验
增加 `TraderSelectionPolicy` 类（G04）；`add_to_listed` 方法增加前置校验。

### 4. §3.15 跟单引擎 — 增加 margin_mode 和过期区分
`BotConfig` 增加 `margin_mode`（G07）；`on_signal` 增加过期订阅的动作级别过滤（G10）。

### 5. §3.17 订单执行器 — 增加 set_margin_mode 调用
`OrderRouter.place` 在下单前调用 `set_margin_mode`（G07）。

### 6. §4.2 核心字段表 — 多处扩展
- TraderProfile 增加 `roi_90d, roi_all, trading_days, win_rate_all`（G05）
- CopyBot 增加 `margin_mode`（G07）
- 新增 `contract_spec` 表（G08）
- 新增 `platform_pool` 表（G06）
- 新增 `mini_account, mini_account_tracking` 表（G14）
- PaymentOrder 确认 ERC-20 支持（G09）

### 7. §6.5 支付校验 — 增加超时邮件
`mark_timeout` 方法增加 `mailer.send`（G19）。

### 8. §6.6 奖励触发 — 增加 48h 延长
`credit` 方法增加风控检测和动态核实期（G11）。

### 9. §7.1 用户前台接口 — BalanceSnapshot 扩展
`/v1/rewards/me` 响应增加 `frozen` 字段（G12）。

### 10. §7.3 后台接口 — 策略列表增加运维字段
`/admin/v1/signals/{exchange}` 响应增加 `source_mode, mini_account_id, ws_status` 等（G15）。

### 11. §8 关键安全约束 — 增加合约级精度
`compute_size` 从交易所级参数改为合约级参数（G08）。

### 12. 新增 §13 — 首页资产聚合策略
增加 `AccountOverviewService` 的三层缓存策略（G18）。

---

## 对开发计划的具体修订指令

### M1 修订
- T1.1 增加 `platform_pool` 表迁移（G06）
- T1.4 IdentityService 增加 `platform_pool` 自动检测逻辑（G06）

### M2 修订
- T2.1 适配器增加 `ScraperConfig`（代理池 + 随机间隔）（G17）
- T2.2 NormalizedSignal 增加 `action` 枚举（G03）；增加 `NoiseFilterConfig`（G02）
- T2.3 TraderProfile 增加 `roi_90d, roi_all, trading_days, win_rate_all`（G05）
- T2.6 增加 `TraderSelectionPolicy` 门槛校验（G04）

### M3 修订
- T3.1 CopyBot 增加 `margin_mode` 字段（G07）；新增 `contract_spec` 表（G08）
- T3.4 `compute_size` 参数从交易所级改为合约级（G08）
- T3.5 风控规则增加"过期订阅动作级别过滤"（G10）
- T3.6 OrderRouter 增加 `set_margin_mode` 调用（G07）

### M4 修订
- T4.3 即时校验范围改为 TRC-20 + BEP-20 + **ERC-20**（G09）
- T4.4 轮询增加 ERC-20 阈值 12（G09）；增加超时邮件通知（G19）
- T4.5 LedgerService 增加 48h 风控延长逻辑（G11）
- T4.6 最低提现门槛统一为 **10U**（G13）；手续费口径统一（G20）
- T4.8 ERC-20 RPC 工期从 1.5d 调至 2d（G09）
- T4.11 BalanceSnapshot 增加 `frozen` 字段（G12）

### M5 修订
- T5.4 信号源管理增加运维看板字段（G15）
- T5.13 首页 4 卡增加缓存策略（G18）

### V2 预留（新增）
- V2-A：MiniAccount 表 + WS 管理器 + REST 补单（G14 + G16）
- V2-B：按带单员订阅 Plan（G01）

---

## 文档管理

- 本分析文档路径：`.trae/documents/2026-08-12-signal-saas-design-gap-analysis.md`
- 后续动作：按"修订指令"回写设计文档和开发计划
- 验收标准：每条差异（G01-G20）在设计文档或开发计划中有对应修复确认

---

> 本文档完成于 2026-08-12；共 20 条差异，11 条 🔴 必须修复，7 条 🟡 建议修复，2 条 🟢 可后置。

---

## 执行状态补充（2026-08-16）

本文档所列后台相关差异与后续新增要求已落地，核对结果：

- **后台 UI 全部对齐演示 HTML**：登录 / 数据概览 / 用户管理 / 主号审核 / 信号源审核 / 跟单订单 / 支付记录 / 邀请奖励 / 钱包账本 / 提现审核 / 交易所邀请码 / 风控中心 / 审计日志 / 信号源登录 共 13 页，按 `docs/2026-08-12-signal-saas-admin-*.html` 蓝本逐页重写，Playwright 端到端 13/13 通过、0 JS 错误。
- **TOTP 双因素（原 V1.1 后置项）已实现**：pyotp + Redis 挑战码一次性验证；`totp-verify` / `totp/setup` / `totp/confirm` / `totp/disable` 四个端点；连续 5 次密码错误锁定 15 分钟。详见 `OPERATIONS_RUNBOOK.md` §8。
- **CORS 中间件顺序修复**：429 限流响应原先绕过 CORSMiddleware 导致浏览器报 `No 'Access-Control-Allow-Origin'`，调整注册顺序后限流错误可正常透传前端。
- **信号源登录页完善**：状态 KPI + 三步引导 + 远程浏览器视图工具栏 + 带单员搜索（`/signal-session/search` 由 API 暴露至 UI）。
- **支付接口补充**：`/admin/v1/payments` 列表响应新增 `created_at` 字段（供数据概览"今日支付额"统计）。

### 前台页面对齐（2026-08-16，追加）

前台 9 个业务页面按 `docs/2026-08-12-signal-saas-*.html` 蓝本补齐，Playwright 端到端 9/9 通过、0 JS 错误：

- **全站共性**：6 层信号宇宙背景（aurora/grid/dots/sweep/noise/particles）、页面容器 1240px、顶栏（品牌 logo + 通知铃铛下拉 + 用户 chip）、全局组件类（panel / ftx-table / badge / kpi-grid / chip / filter-bar / pagination / action-tag / toast）。
- **登录/注册**：左侧品牌区双栏 + 玻璃拟态认证卡 + 登录/注册 Tab + 忘记密码入口（后端无接口，提示型）；注册 3 步指示器 + 条款勾选 + 密码强度 + 验证码倒计时 + 注册成功/风险揭示 + 首次引导 5 步（选所 → G27 交易所邀请码 → 好友码 → 完成）。
- **策略广场/详情/我的跟单**：策略卡 spark 迷你曲线 + chip 筛选 + 页码分页 + 风格彩色标签；详情 hero 大卡 + 持仓卡片化 + 交易表 7 列 + 跟单弹窗高级字段（方向/保证金模式/单笔上限）；我的跟单暂停/恢复确认弹窗 + G10 订阅过期横幅 + 卡片 2×2 参数网格 + 空态引导。
- **邀请/奖励/提现/账户/订阅**：邀请 10% Hero + 核实时间轴（倒计时/进度条）+ 收益趋势图 + 流水明细表 + 规则说明 + 5 统计卡；奖励可提现高亮首卡 + 流水 6 列 + 页头提现按钮；提现余额卡 + 二次确认弹窗 + 双栏布局；账户侧栏 4 Tab（概览/API/选所/安全）+ API 卡片 + 绑定弹窗；订阅正式版推荐标签 + 订阅状态卡（进度条/续费）+ 支付状态机 UI（pending 倒计时 / verifying 进度 / confirmed / failed / timeout / manual）+ G10 过期黄条。
- **修复**：account 页 useState 初始化读 localStorage 导致 SSR hydration 报错（React #418），改为 useEffect 内读取。
- **测试数据**：通过后台 API 从待选池上架 2 个策略（trader 30585 / 30879），供前台策略广场与详情展示。
