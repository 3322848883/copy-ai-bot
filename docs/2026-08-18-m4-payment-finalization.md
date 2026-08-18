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

## 关联文档
- 平台设计 / 需求编号：`docs/2026-08-12-signal-saas-platform-design.md`（G09 链上确认、G13 提现、G27 订阅支付）
- 上线清单 / 运维：`docs/PRODUCTION_CHECKLIST.md`、`docs/OPERATIONS_RUNBOOK.md`