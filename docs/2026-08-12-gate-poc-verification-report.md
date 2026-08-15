# Gate 官方直连 POC 验证报告

> 日期：2026-08-12
> 目的：验证决策 B（直接对接 Gate 官方 API，弃用 ccxt）的核心可行性
> 环境：Docker python:3.11-slim + requests + websocket-client，密钥经环境变量注入

## 验证结论速览

| POC | 验证项 | 结果 |
|-----|--------|------|
| POC-1 | 密钥连通性 + 签名算法（HMAC-SHA512） | ✅ 通过 |
| POC-2 | 合约规格数据源（ContractSpec 表字段来源） | ✅ 通过 |
| POC-3 | 私有 WebSocket 回报（模式 B 核心 / 成交回报） | ✅ 通过 |
| POC-4 | 小额真实下单 + 撤单 | ⛔ 受账户资金状态阻塞，未执行 |

## POC-1 密钥连通性与签名算法 — 通过

- 调用 `GET /spot/accounts` 返回 **HTTP 200**。
- 现货账户：`USDT 0.0000002471`、`GT 0.0023500462`。
- **密钥有效、签名算法正确、官方直连跑通。**
- 关键修正：Gate 官方签名串为
  `HMAC-SHA512(secret, METHOD\nPATH\nQUERY\nSHA512_HEX(body)\nTIMESTAMP)`，
  末尾**必须追加 TIMESTAMP**，且该时间戳需与请求头 `Timestamp` 一致。最初遗漏时间戳返回 `INVALID_SIGNATURE`。
- 三个认证头：`KEY`、`Timestamp`、`SIGN`。
- 合约账户接口返回 `USER_NOT_FOUND` 属正常提示（账户未创建，见 POC-4a）。

## POC-2 合约规格数据源 — 通过

- `GET /futures/usdt/contracts`（**公开接口，无需签名**）返回 **HTTP 200**，共 **907 个合约**。
- 示例 `BTC_USDT` 关键字段：
  - `quanto_multiplier = 0.0001`（面值，每张 0.0001 BTC）
  - `order_size_min = 1`（最小下单量）、`order_size_max = 12000000`
  - `mark_price_round = "0.01"`（价格精度）
  - `enable_decimal = false`（BTC 用整数张数）
  - `leverage_max = 200`
- **结论**：公开接口可直接支撑 `ContractSpec` 表初始化，无需签名，适合前端选币/选合约与后台数据同步。
- **字段映射**：`face_value_usdt` 需由 `quanto_multiplier` × 当前价格换算；`size_precision` 由 `enable_decimal` + `order_size_interval` 决定。

## POC-3 私有 WebSocket 回报 — 通过

- 端点：`wss://fx-ws.gateio.ws/v4/ws/usdt`（合约 USDT 本位实盘）。
- **认证方式**：无需 REST 换 token，直接在订阅请求的 `auth` 字段内签名。
  - 签名串：`channel=<c>&event=<e>&time=<t>`
  - `auth = {"method": "api_key", "KEY": key, "SIGN": hex(HMAC_SHA512(secret, 签名串))}`
- 成功订阅 `futures.orders`（`["!all"]`）与 `futures.usertrades`（`["!all"]`），均返回 `status: success`。
- 收到 1 条回报事件，心跳 `futures.ping` 正常。
- **结论**：私有 WS 认证与回报链路验证通过，可支撑成交回报与模式 B 信号跟踪。
- 注：`futures.positions` 订阅需用户 ID，payload 为 `["<user_id>", "<contract>"]`。

## POC-4 小额真实下单 — 未执行（账户资金阻塞）

### 下单前账户检查（POC-4a）

| 项 | 值 | 说明 |
|----|-----|------|
| 现货 USDT | 0.0000002471 | 约 0 余额 |
| 现货 GT | 0.0023500462 | 非结算币种 |
| 合约账户 | `USER_NOT_FOUND` | **未创建**，需先入金 |
| 合约账本 | 空 | 无交易历史 |
| BTC_USDT 价格 | 64040.8（公开 ticker） | 价格接口可用 |

### 阻塞原因

1. **现货 USDT 不足**：无法转入合约账户创建合约账户。
2. **合约账户未创建**：`please transfer funds first to create futures account`。
3. 在无资金、无合约账户状态下无法执行真实下单。

### 后续步骤（待用户补充资金后）

1. 向现货转入至少 20-50 USDT。
2. 现货→合约账户转账（`POST /futures/usdt/accounts` 或钱包转账接口）。
3. 用最小单量（1 张 BTC_USDT 合约）下一张**限价单**（价格设在远离市价处，确保不成交），验证下单→撤单链路，再撤单。
4. 可选：用券商子账户/测试网（`wss://ws-testnet.gate.com`）做无风险验证。

## 对框架/开发计划的验证结论

| 原设计假设 | 验证结果 | 影响 |
|-----------|---------|------|
| 官方直连可行（决策 B） | ✅ Gate 一家已跑通 | 可推进其余 4 家（Binance/OKX/Bybit/Bitget） |
| 签名自研可控 | ✅ HMAC-SHA512 已实现 | 框架 `exchange_clients/signing.py` 落地 |
| ContractSpec 表数据源 | ✅ 公开接口可取 | 902 个合约可初始化 |
| WS 回报自研 | ✅ 私有 WS 认证+订阅通过 | 框架 `ws_client.py` 落地 |
| 合约规格字段映射 | ⚠️ 需自换算面值 | 设计补充 `quanto_multiplier→face_value` 换算 |

## 遗留待办

- [ ] 用户补充现货 USDT 资金后执行 POC-4 真实下单验证
- [ ] 建议重置已明文暴露的 Gate API key（本次验证的密钥）
- [ ] 将验证通过的签名/WS 代码沉淀为框架 `exchange_clients/gate_client.py` 骨架