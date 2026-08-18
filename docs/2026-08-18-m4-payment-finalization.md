# 支付板块收尾（M4 补强）：四链支付 + 邮件 SMTP 后台化 + 假按钮清理

> 日期：2026-08-18
> 范围：在既有「多链 USDT 支付 + 自动核实」基础上补齐真实生产支付能力，处理支付板块的假数据与假按钮，并把邮件 SMTP 参数收口到后台可配。

## 一、四链支付（新增 APTOS，原三链 → 四链）

支付网络由 `trc20 / bep20 / erc20` 扩展为 `trc20 / bep20 / erc20 / aptos`，从前台订阅、后台支付记录、后台收款地址管理到提现全部贯通。

### 1. 配置（`api/core/config.py`）
- `aptos_rpc_url`：Aptos fullnode REST API（默认 `https://fullnode.mainnet.aptoslabs.com/v1`）。
- `aptos_usdt`：APTOS 上的 USDT 资产类型（LayerZero / Bridge 桥接标准合约，6 位小数）：
  `0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDT`。

### 2. 链客户端（`api/services/payment/chain_client.py`）
新增 `AptosClient(ChainClient)`：

- **确认数计算**：APTOS 无 EVM 区块概念，交易 `version` 即链上序号段；用 fullnode root 接口的 `ledger_version` 计算
  `confirmations = ledger_version - tx_version + 1`。
- **入账校验**：APTOS 无 EVM `Transfer` 事件，桥接 USDT 走 coin module，入账表现为发往收款地址的
  `0x1::coin::DepositEvent<USDT>`；按事件 guid 的 `account_address` == 收款方且金额 ≥ 应收金额判定到账。
- **错误三态语义** 同 TronClient（`unconfirmed` / `network_error` / `failed`）；404 交易不存在视为未上链继续轮询。
- **确认阈值**：`REQUIRED_CONFIRMATIONS["aptos"] = 20`；`USDT_CONTRACT["aptos"]` 指向桥接资产类型。

### 3. 后台可配确认数
`api/services/settings/service.py` 新增 `chain_confirm_aptos`（默认 20），随 `get_chain_confirmations()` 一并读取。

### 4. 地址格式校验
- 后台收款地址管理（`api/routers/admin/payments.py`）：`_APTOS_RE = ^0x[a-fA-F0-9]{1,64}$`（canonical 0x + 变长 hex，去前导 0）。
- 前台提现（`api/routers/v1/withdrawals.py` + `api/services/withdrawal/service.py`）：
  `network` 限定加入 `aptos`，`APTOS_RE` 同规则；address 长度放宽到 `3~128`。

### 5. 前端
- 订阅页（`web-ui/app/subscriptions/page.tsx`）：网络选择加入 APTOS（20 确认），标题"三链"→"四链"。
- 后台支付记录（`web-admin/app/payments/page.tsx`）：APTOS 网络标签 + 配色，标题"三链"→"四链"。
- 后台收款地址管理 placeholder 补充 APTOS 说明。
- 提现页（`web-ui/app/withdraw/page.tsx`）：新增 APTOS 网络选项。
- 邀请中心规则说明（`web-ui/app/invite/page.tsx`）：提现支持链路更新为四链。

## 二、邮件 SMTP 参数后台化

原 SMTP 参数仅读 `.env`，现收口到「系统设置 → 邮件」后台可配，未覆盖时兜底沿用 `.env` 默认值。

### 后端（`api/services/settings/service.py` / `api/services/mailer/service.py`）
- 新增规则：`smtp_host / smtp_port / smtp_user / smtp_password / mail_from`，默认值分别取自环境变量。
- `smtp_password` 为**密钥型规则**（`_SECRET_KEYS`）：读取回显脱敏为占位 `********`；留空 / 占位掩码保存时不覆盖（保留原值）。
- `Mailer._send_smtp` 改为从 `settings_svc.get_rule` 动态读取，覆盖 `.env`。

### 后台界面（`web-admin/app/settings/page.tsx`）
- 新增 `str` 规则类型支持文本/密码输入；`secret` 字段密码框 + 留空保留原值。
- 「邮件」分组描述更新，覆盖 mail 与 smtp 前缀字段。

### 审计脱敏（`api/routers/admin/settings.py`）
- 对含 `password` 的设置项，审计 before/after 均落 `********`，不落明文凭据。

## 三、支付订单历史接口 + 前端"查看记录"弹窗

- 新增 `GET /v1/payments/orders`（`api/routers/v1/payments.py`）：返回当前用户支付订单历史，limit 默认 20，按 id 倒序。
- 订阅页"查看记录"按钮（原为假 toast）改为加载并弹窗展示历史订单，含套餐 / 金额 / 网络 / 状态（含确认进度 `confirmations/required`）/ 创建时间。

## 四、假按钮清理

按「支付板块、前端界面不能有假按钮」要求，移除以下仅有提示文案、无真实后端动作的交互：

| 位置 | 移除项 | 处理 |
|---|---|---|
| 登录页 | "使用邮箱验证码登录"按钮 | 移除（后端无该登录方式，保留密码/注册入口） |
| 登录页 · 忘记密码 | "发送验证码"冒充重置流程 | 收敛为静态提示：自助重置暂未开放，联系管理员 |
| 注册页 | "重新发送"/"xs 后重发"按钮 | 移除（后端无独立 resend 端点），改为提示性文案 |
| 个人中心 · API | "重新校验"按钮 | 移除（实时已校验，不应再提供假动作） |

## 五、验证码用途隔离（为后续 forgot/reset 预留）

`api/services/auth/service.py`：验证码 Redis key 按用途隔离（`verify`=注册/登录，`reset`=重置密码），内存兜底 key 亦区分用途，为将来开放自助重置密码铺路（当前登录/注册验证码行为不变）。

## 六、本地生产测试 CORS（`docker-compose.prod.local.yml`）

本地生产栈放行 `http://localhost:3001,3002`（后台/前台）跨源：设 `CORS_ALLOW_LOCAL_TEST=1` + 显式 `CORS_ORIGINS`（prod 默认仍拒绝 localhost，仅本地测试栈放开）。

## 七、配套脚本（`scripts/`）

- `_chain4_paytest.py`：dev 环境四链（trc20/bep20/erc20/aptos）支付下单→提交交易→查单 全链路联调。
- `_clean_payment_fake.py`：清理 dev/prod 两库中的用户侧假数据，按依赖序删除用户相关表，保留真实收款地址并补齐缺口。
- `_prod_payment_poller.py`：独立支付轮询器，周期扫描 `verifying / polling` 状态的订单并按链确认。
- `_sync_aptos_dev.py`：把真实 APTOS 收款地址同步到 dev 库。
- `scripts/seed_demo.py`：演示数据补入 dev APTOS 收款地址。

## 八、H4 支付入账加固（真金实测驱动，2026-08-18 下午）

真金转账实测（交易所提现 2U → Aptos 到账 1.96U → 订单 1.0U）暴露的问题与修复：

| # | 问题 | 修复 | 位置 |
|---|---|---|---|
| 1 | Aptos 新版钱包走 `fungible_asset::Deposit`（Petra 默认），旧实现只认 `coin::DepositEvent` → 真实转账被判失败 | FA 事件三重反查：`store → ObjectCore.owner`（收款方）`→ FungibleStore.metadata → Metadata.symbol == "USDT"`（资产） | `chain_client.py AptosClient.validate_tx` |
| 2 | 交易所提现手续费链下扣除，实际到账 ≠ 订单金额 | 校验保持**足额即认**（≥），同时把**实际到账精确落库** `paid_amount_usdt`（超额可见/可对账） | `validate_tx` 返回 `(ok, reason, received)`；`payment_orders.paid_amount_usdt`；`/v1/payments/orders` 序列化 |
| 3 | 平台地址链上公开 → 任何人可用**链上历史他人付款**的哈希激活新订单（H1 查重只挡系统内用过的哈希） | **交易时间窗 15 分钟**：tx 上链时间 ≥ 订单创建 -900s（覆盖"先付款再下单"的用户，交易所提现到账常需数分钟）；更早即拒绝且订单保持 pending 可重提；未来时间 >+300s 拒绝 | 四链新增 `get_tx_timestamp`；`submit_tx` H4-2 |
| 4 | 并发双提交 / 与 poll_sweep 竞争同一订单可双开通 | **行级锁** `SELECT ... FOR UPDATE` + `_confirm` 原子 CAS（H3 已有）+ **tx_hash 唯一部分索引**（DB 层第二道防线） | `submit_tx` H4-1；迁移 `b2c3d4e5f6a7` |
| 5 | pending 订单 TTL 30 分钟无清理，永久悬挂 | `payment.expire_sweep` Beat 任务（每 2 分钟）批量置 `expired` | `tasks_payment.py` + `celery_app.py` |
| 6 | 交易所提现**从本金扣手续费** → 实际到账 < 订单金额（如提 20U 付 19.9U 订单，TRC20 扣 1.8U 到账 18.2 被拒） | **手续费容差**：入账下限 = max(订单金额 - 容差, 订单金额×50%)，容差规则 `payment_fee_tolerance_usdt` 默认 2.0（后台可调）。2026 实测依据：OKX TRC20 ~1.8U（非 ERC20 最坏）、币安 TRC20 ~1.0U、BEP20 ~0.2-0.3U、Aptos ~0.04U。冷钱包直转 gas 用 TRX/BNB/ETH/APT 另付、USDT 全额到账不占容差 | `_verify_value`；`services/settings/service.py` |
| 7 | **BSC-USDT 是 18 位小数**（ETH 是 6 位），硬编码 /10**6 → 金额放大 10^12 倍 → 转真实 0.000001 USDT 即可激活任意订单（**严重漏洞**） | 按链查 `USDT_DECIMALS`（trc20=6/bep20=18/erc20=6/aptos=6） | `chain_client.py` |
| 8 | EVM/Tron 只看**第一笔** Transfer 事件/第一页转账腿 → 多腿交易（路由、交易所批量提现）误拒真实付款 | 遍历**全部**事件匹配 (to, amount)；Tron 按哈希反查**翻页**（limit 上限 50，上限 2000 腿） | `EvmClient.validate_tx`；`TronClient.validate_tx` |
| 9 | BSC 是 POA 链，web3 `eth_getBlock` 因 extraData>32 字节直接抛异常 → **BEP20 确认数永远失败** | 注入 `ExtraDataToPOAMiddleware`（仅 bep20） | `EvmClient._w3_list` |
| 10 | 公共 RPC 限流（bsc.publicnode.com 实测 403）→ 支付校验/确认随机失败 | 主节点 + 3 备用节点依次回退（bep20: meowrpc/blockrazor/1rpc；erc20: merkle/1rpc/ankr）；主节点已换 `bsc-rpc.publicnode.com` | `_RPC_FALLBACKS`；`docker-compose.prod.local.yml` |
| 11 | Tron 时间戳：trongrid 免费档限流返回空 → 时间窗被静默跳过；tronscanapi 字段名是 `timestamp` 非 `blockTimestamp` | 改走 tronscanapi `transaction-info` 的 `timestamp` 字段（与 validate_tx 同源） | `TronClient.get_tx_timestamp` |

**#7-#11 为 H5 修复（2026-08-19）**：Aptos 真金验证后，对 trc20/bep20/erc20 用**真实链上转账数据**零成本回归（不花钱、直接跑生产校验函数）发现——已全部修复并复验：三链 validate_tx / get_tx_timestamp / get_confirmations 全部 `ok=True`，时间戳 sanity、确认数正常（含主节点 403 时备用节点自动接管）。

**状态机**：`pending → verifying → polling → confirmed / failed / manual / expired`。

**实测记录**：
- FA 路径：`validate_tx → (True, '', 1.96)` ✓
- H1 重放：新订单提交已用哈希 → `该 TxHash 已被其他订单使用` ✓
- H4-2 时间窗：43.8 分钟前的真实哈希对新建订单 → REJECT ✓（15 分钟窗语义复算验证）
- 容差：规则值 2.0 ✓；1U 订单下限 0.5U、19.9U 订单下限 17.9U ✓；真实 1.96 交易 vs 下限 0.5 通过、vs 17.9 拒绝 ✓
- expire sweep：手动执行 `expired 0 orders (ttl=30min)` ✓；beat 注册 `payment-expire` 并真实触发 ✓

**运维注意**：
- Celery Beat 默认 PersistentScheduler（`celerybeat-schedule` 文件缓存调度表）——**新增/修改 beat 任务后必须删除该文件并重启 beat**，否则新任务不生效。
- 超额部分（如 1.96 - 1.0 = 0.96）目前仅落库可见，不做自动找零/入余额；如需余额/抵扣体系为后续产品迭代。
- Tron 校验走 tronscanapi（第三方）；如需去第三方依赖可切换 trongrid 内部交易解析（未实施）。
- **ERC20 大额提现费（3.5~10U）超出 2U 容差**：小额订单不建议 ERC20（支付页建议用户走 TRC20/BEP20/Aptos）；如需覆盖可在后台把 `payment_fee_tolerance_usdt` 调大，但 50% 下限始终兜底。
- 容差与时间窗均为后台可调/代码常量：容差规则 `payment_fee_tolerance_usdt`（后台设置-支付订单组）；时间窗 900s 为 `service.py` 常量。

## 关联文档
- 平台设计 / 需求编号：`docs/2026-08-12-signal-saas-platform-design.md`（G09 链上确认、G13 提现、G27 订阅支付）
- 上线清单 / 运维：`docs/PRODUCTION_CHECKLIST.md`、`docs/OPERATIONS_RUNBOOK.md`