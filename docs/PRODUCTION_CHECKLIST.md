# signal-saas 上线检查清单（M6 T6.7）

> 进入生产前逐项打勾；任何一项不满足不得放量。

## 1. 环境变量（生产必填，缺失即启动失败）

| 变量 | 说明 | 必填 |
|---|---|---|
| `APP_ENV` | `prod` | ✅ |
| `JWT_SECRET` | ≥32 位随机串（config 校验拒绝默认值） | ✅ |
| `VAULT_KEY_HEX` | 64 位 hex 随机主密钥（非全 0） | ✅ |
| `DATABASE_URL` | 生产 PG 连接串（拒绝本地默认串） | ✅ |
| `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/MAIL_FROM` | 生产 SMTP（拒绝 mailhog） | ✅ |
| `CORS_ORIGINS` | 精确域名白名单（禁止 `*`/`localhost`；须含前台域名 + 后台子域） | ✅ |
| `SITE_DOMAIN` | 前台主域名（nginx 反代 + TLS） | ✅ |
| `ADMIN_SUBDOMAIN` | 后台子域（独立 SPA 入口；证书须覆盖该子域） | ✅ |
| `ENABLED_EXCHANGES` | V1 仅 `gate` | ✅ |
| `TRON_RPC_URL/BSC_RPC_URL/ETH_RPC_URL/APTOS_RPC_URL` | 四链上链 RPC（主 + 3 备自动故障切换；建议自建/付费节点） | ✅ |
| `BROWSER_PROXY_URL` | 浏览器采集代理；海外服务器留空，国内必配（详见 `docs/2026-08-18-browser-proxy-deployment.md`） | 视网络 |
| `POSTGRES_PASSWORD` | 生产 DB 密码（compose 强制） | ✅ |
| `GRAFANA_ADMIN_PASSWORD` | Grafana 管理员密码（compose 强制） | ✅ |

## 2. 平台收款地址（后台维护，非环境变量）

- [ ] 登录后台「订单管理 → 平台收款地址」配置 TRC-20 / BEP-20 / ERC-20 / APTOS 四条 active 地址
- [ ] 地址格式校验（T 开头 34 位 / 0x+40 hex EVM / Aptos 0x+64 hex）；未配置的链用户提交时返回"暂未开放收款"
- [ ] 四链小额真实资金入账验证（Aptos 已端到端验证；BEP20 改动最多，建议 1U 复验）

## 3. 监控告警阈值（计划 §7.3 六指标，Grafana 看板 signal-saas）

> 已固化：`deploy/grafana/provisioning/alerting/alerting.yml`（6 条规则，Grafana 启动自动加载）。

| 指标 | 告警阈值 |
|---|---|
| `signal_received_total` | 5min 跌 0（信号源中断） |
| `risk_decisions_total{decision="rejected"}` | rejected 占比 >30% |
| `app_copy_orders_filled_total / _failed_total` | failed 占比 >10% |
| `payment_poll_attempts_total` | 单链轮询 >5/min（RPC 异常） |
| `withdrawal_pending_total` | >100 持续 1h |
| `http_request_duration_seconds` | p95 > 1s |

- [x] 告警规则已配置（6 条，见 `alerting.yml`）
- [ ] 配置通知渠道（Alerting → Contact points，绑定邮箱/飞书/钉钉）

## 4. 密钥轮换演练（每季度）

> 已固化：`scripts/rotate_vault_key.py`（旧密钥解密→新密钥重加密，任一失败整体回滚）。详见 `docs/OPERATIONS_RUNBOOK.md` §3。

- [ ] `JWT_SECRET` 轮换：更新 env → 滚动重启（旧 token 失效，用户重新登录可接受窗口内完成）
- [ ] `VAULT_KEY_HEX` 轮换：**先解密存量 API Key 再换新密钥重加密**（`rotate_vault_key.py` + 灰度一个用户验证）
- [ ] 演练记录留档

## 5. 备份与恢复演练（每月）

> 已固化：`scripts/backup_pg.sh`（备份+保留14份）、`scripts/restore_pg.sh`（恢复到全新库+冒烟）。详见 `docs/OPERATIONS_RUNBOOK.md` §2。

- [ ] `scripts/backup_pg.sh` cron 每日 03:00（保留 14 份）
- [ ] Redis `appendonly yes`（prod compose 已开启 ✅）
- [ ] 恢复演练：新库 `pg_restore` 全量恢复 + 冒烟（登录/跟单/支付）
- [ ] 演练记录留档

## 6. 灰度放量（前 50 用户手动审核）

- [ ] 前 50 注册用户人工审核（邮箱/来源/邀请关系）
- [ ] 7 天观察期：监控指标无异常、无刷单预警
- [ ] 按 20% → 50% → 100% 逐步放量（后台策略 gray_pct）

## 7. 回滚方案

- [ ] 镜像打 tag（git commit sha），可回滚上一版本
- [ ] 回滚步骤：`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate api worker beat consumer`
- [ ] 数据库变更仅前向（Alembic）；需回滚时人工介入评估

## 7.5 浏览器采集网络（gate.com 打通）

> 完整决策表与步骤见 `docs/2026-08-18-browser-proxy-deployment.md`。

- [ ] 容器内实测 gate.com：可达（200）→ `BROWSER_PROXY_URL` 留空；不可达 → 按国内场景配置
- [ ] 国内 + Docker：中继 `scripts/proxy_relay.py` 已 systemd 常驻（`signal-relay.service`，Restart=always）
- [ ] 中继端口（默认 17897）防火墙仅放行 Docker 网段（`172.17.0.0/16`），拒绝公网（⚠️ 否则=开放代理）
- [ ] Linux 服务器确认 compose `extra_hosts: host.docker.internal:host-gateway` 生效（prod.local.yml 已带）
- [ ] 验证：worker 日志 `launch ... proxy=http://...` 且无 `ERR_CONNECTION_CLOSED`；`signal.poll_live ... succeeded`
- [ ] 非 Docker 部署：`.env` 直接 `BROWSER_PROXY_URL=http://127.0.0.1:7897`（无需中继）

## 8. 压测记录（T6.3）

> 已固化：`loadtest/loadtest.py`（并发混合负载：登录/策略/看板/提现，输出 `docs/loadtest-report.html`）。详见 `docs/OPERATIONS_RUNBOOK.md` §4。

- [ ] 100 并发用户 30min，p95 延迟 < 500ms（`python loadtest/loadtest.py --base-url <url> --users 100 --duration 1800`）
- [ ] 报告存档（`docs/loadtest-report.html`）

## 9. 合规（T6.1）

- [x] 风险揭示文案已强制（登录 + 首次跟单）
- [x] 隐私政策 / 服务条款页面上线（`/privacy`、`/terms`，内容为非占位模板）
- [ ] 外部法务复核通过（上线前独立交付）

## 10. 后台安全（TOTP 双因素 + 登录锁定）

> TOTP 已实现（pyotp RFC6238 + Redis 挑战码）。V1 管理员默认直登，逐账号绑定双因素后强制。

- [ ] 管理员账号逐个启用 TOTP（`POST /admin/v1/auth/totp/setup` 获取密钥 → 身份验证器扫码 → `confirm` 激活）
- [ ] 高危操作管理员（admin 角色）全部绑定双因素后，生产环境配置 `ADMIN_TOTP_REQUIRED=true`（预留开关）
- [ ] 确认登录锁定生效：连续 5 次密码错误 → 15 分钟锁定（Redis `admin:login_lock:{email}` 自动过期）
- [ ] 确认登录页文案与锁定提示（剩余尝试次数 / 锁定说明）正常展示
- [ ] 演练：TOTP 动态码过期/错误 → 拒绝并提示；`totp-verify` 挑战一次性使用（重复提交失败）

## 11. 上线全局核查（2026-08-19 完成，四批 commit）

> 逐功能前台后台对照检查的修复明细与冒烟记录见 `docs/2026-08-19-production-hardening.md`。
> commits：`fa82d81`（品牌+公告+配置端点）→ `91d6b30`（P0×3+P1×5）→ `b31e139`（构建上下文瘦身）→ `b3bf20f`（P1/P2 收尾）。

- [x] P0：submit_tx 三态分流（未上链/RPC 故障转轮询，不再误判失败）；种子脚本弱口令兜底清除；提现链上校验下限改净额
- [x] P1：订单 TTL 内联校验 + 过期禁提交；风控命中奖励 frozen 落库；邀请统计按 Reward 状态精确聚合；APTOS_TX_RE 正则；跟单固定金额输入
- [x] P1 收尾：审计筛选服务端化（danger/action/actor_id）；人工确认支付行锁+CAS；跟单引擎虚拟锁定精算 + 订阅闸门 fail-closed；信号差分 Redis 互斥锁防双发；confirmed 对账补偿任务；`APP_ENV` 默认 prod fail-fast；用户管理分页 + 服务端状态筛选；订单 KPI 今日口径；高危用户冻结奖励真实聚合；前台 7 处 UTC 时区修复
- [x] P2：withdraw 不再编造驳回原因；法务页草稿声明清理；死代码/假状态卡清理（模式 B 卡、G27 内部码等）
- [ ] 遗留（人工操作）：后台「系统设置」填客服邮箱/TG；SMTP `MAIL_FROM` 改实际发信域名；BEP20 1U 真实资金复验（建议）
