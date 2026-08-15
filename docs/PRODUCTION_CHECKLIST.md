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
| `CORS_ORIGINS` | 精确域名白名单（禁止 `*`） | ✅ |
| `ENABLED_EXCHANGES` | V1 仅 `gate` | ✅ |
| `TRON_RPC_URL/BSC_RPC_URL/ETH_RPC_URL` | 链上 RPC（建议自建/付费节点） | ✅ |
| `POSTGRES_PASSWORD` | 生产 DB 密码（compose 强制） | ✅ |
| `GRAFANA_ADMIN_PASSWORD` | Grafana 管理员密码（compose 强制） | ✅ |

## 2. 平台收款地址（后台维护，非环境变量）

- [ ] 登录后台「订单管理 → 平台收款地址」配置 TRC-20 / BEP-20 / ERC-20 三条 active 地址
- [ ] 地址格式校验（T 开头 34 位 / 0x+40 hex）；未配置的链用户提交时返回"暂未开放收款"

## 3. 监控告警阈值（计划 §7.3 六指标，Grafana 看板 signal-saas）

| 指标 | 告警阈值 |
|---|---|
| `signal_received_total` | 5min 跌 0（信号源中断） |
| `risk_decisions_total{decision="rejected"}` | rejected 占比 >30% |
| `app_copy_orders_filled_total / _failed_total` | failed 占比 >10% |
| `payment_poll_attempts_total` | 单链轮询 >5/min（RPC 异常） |
| `withdrawal_pending_total` | >100 持续 1h |
| `http_request_duration_seconds` | p95 > 1s |

## 4. 密钥轮换演练（每季度）

- [ ] `JWT_SECRET` 轮换：更新 env → 滚动重启（旧 token 失效，用户重新登录可接受窗口内完成）
- [ ] `VAULT_KEY_HEX` 轮换：**先解密存量 API Key 再换新密钥重加密**（脚本演练 + 灰度一个用户验证）
- [ ] 演练记录留档

## 5. 备份与恢复演练（每月）

- [ ] `scripts/backup_pg.sh` cron 每日 03:00（保留 14 份）
- [ ] Redis `appendonly yes`（prod compose 已开启）
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

## 8. 压测记录（T6.3）

- [ ] 100 并发用户 30min，p95 延迟 < 500ms
- [ ] 报告存档（`docs/`）

## 9. 合规（T6.1）

- [ ] 风险揭示文案已强制（登录 + 首次跟单）
- [ ] 隐私政策 / 服务条款页面上线（`/privacy`、`/terms`）
- [ ] 外部法务复核通过（上线前独立交付）
