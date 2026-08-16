# signal-saas 上线操作演练手册（M6 T6.7）

> 告警规则、备份恢复、密钥轮换、压测、灰度、回滚的落地步骤。对照 `PRODUCTION_CHECKLIST.md` 逐项执行留档。

## 1. 监控告警（清单 §3，已配置）

- 告警规则：`deploy/grafana/provisioning/alerting/alerting.yml`（6 条，见下表），Grafana 启动自动加载。
- **待办**：进入 Grafana → Alerting → Contact points 配置通知渠道（邮箱/飞书/钉钉），并绑定到 `signal-saas-alerts` 组。

| 规则 | 表达式 | 阈值 |
|---|---|---|
| 信号源中断 | `sum(rate(signal_received_total[5m]))` | `lt 1`，持续 5m |
| 风控拒绝占比 | `if($B==0,0,$A/$B)` A=rejected | `gt 0.3`，持续 10m |
| 跟单失败率 | `if(($A+$B)==0,0,$A/($A+$B))` | `gt 0.1`，持续 5m |
| 支付轮询异常 | `sum(rate(...[1m])) by(network)*60` | `gt 5/min`，持续 5m |
| 待提现积压 | `withdrawal_pending_total` | `gt 100`，持续 1h |
| HTTP p95 | `histogram_quantile(0.95,...)` | `gt 1s`，持续 10m |

## 2. 备份与恢复演练（清单 §5）

**每日备份 cron**（保留 14 份）：
```bash
0 3 * * * cd /opt/signal-saas && POSTGRES_PASSWORD=xxx ./scripts/backup_pg.sh >> /var/log/signal-saas-backup.log 2>&1
```

**月度恢复演练**：
```bash
# 1) 起一个全新空库（本地 5433 端口，避免覆盖生产）
cp docker-compose.prod.yml /tmp/restore-compose.yml   # 改端口为 5433
# 2) 恢复到新库
POSTGRES_PASSWORD=xxx ./scripts/restore_pg.sh backups/signal_saas_<date>.dump
# 3) 冒烟：登录 / 跟单 / 支付端点各打一次，确认返回 200
```
演练记录：恢复的库名、备份时间、冒烟结果、负责人、日期。

## 3. 密钥轮换演练（清单 §4，每季度）

**JWT_SECRET 轮换**：
```bash
export JWT_SECRET=<新 32+ 位随机串>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate api worker consumer
# 旧 access token 立即失效，用户重新登录（可接受窗口内完成）
```

**VAULT_KEY_HEX 轮换**（必须先解密再用新密钥重加密）：
```bash
OLD_VAULT_KEY_HEX=<旧64hex> NEW_VAULT_KEY_HEX=<新64hex> DATABASE_URL=<prod> \
  python scripts/rotate_vault_key.py
# 挑 1 个用户做一次 API Key 绑定连通性验证，确认可正常解密后正式切换 env
```
> 脚本任一记录解密失败即整体回滚，不会产生新旧密钥不一致的中间态。

## 4. 压测（清单 §8，T6.3）

```bash
# 完整验收：100 并发 30min，判定 p95 < 500ms 且成功率 > 99%
python loadtest/loadtest.py --base-url https://api.example.com --users 100 --duration 1800
# 本地冒烟：5 并发 30s
python loadtest/loadtest.py --base-url http://localhost:8000 --users 5 --duration 30
```
报告自动写入 `docs/loadtest-report.html`，归档确认为"通过/未通过+差距"。

## 5. 灰度放量（清单 §6）

1. 前 50 注册用户人工审核（邮箱/来源/邀请关系）。
2. 7 天观察：监控指标无异常、无刷单预警。
3. 后台策略 `gray_pct` 按 20% → 50% → 100% 逐步放量。

## 6. 回滚（清单 §7）

```bash
# 镜像已打 git commit sha tag，可回滚上一版本
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate api worker beat consumer
# 数据库变更仅前向（Alembic）；需回滚时人工介入评估
```

## 7. 合规（清单 §9）

- [x] 风险揭示强制（登录 + 首次跟单）
- [x] 隐私政策 `/privacy`、服务条款 `/terms` 已上线（内容为非占位模板）
- [ ] **外部法务复核**（上线前独立交付，本仓库无法代办）

## 8. 后台双因素（TOTP）运维

**给管理员启用 TOTP**（V1 默认直登，逐账号加固后强制）：

```bash
# 1) 用管理员 access token 获取密钥 + otpauth URI（10 分钟有效）
curl -X POST http://localhost:8000/admin/v1/auth/totp/setup \
  -H "Authorization: Bearer <admin_access_token>"
# → {"secret":"XXXX...","otpauth_uri":"otpauth://totp/signal-admin:1?secret=..."}

# 2) 将 otpauth_uri 生成二维码（或用 secret 手动添加）给管理员扫码入身份验证器（Google Authenticator / Authy / 1Password）

# 3) 用当前动态码确认激活（防误绑）
curl -X POST http://localhost:8000/admin/v1/auth/totp/confirm \
  -H "Authorization: Bearer <admin_access_token>" \
  -d '{"code":"123456"}'
# → {"enabled": true}
```

**停用 TOTP**（找回/换机场景，需当前动态码，防误操作）：

```bash
curl -X POST http://localhost:8000/admin/v1/auth/totp/disable \
  -H "Authorization: Bearer <admin_access_token>" \
  -d '{"code":"123456"}'
```

**启用后的登录流程**：`POST /admin/v1/auth/login` 返回 `totp_required:true + challenge_id`（5 分钟有效）→ 前端进入 6 位动态码步骤 → `POST /admin/v1/auth/totp-verify` 校验通过签发令牌；挑战一次性，重复提交直接拒绝。Redis 键：`admin:totp:{uid}`（密钥）、`admin:totp_challenge:{cid}`（挑战）。

**登录失败锁定**：连续 5 次密码错误锁定 15 分钟（Redis `admin:login_lock:{email}` 自动过期，无需人工解锁；紧急情况下 `redis-cli DEL admin:login_lock:<email>` 手动解除）。

**排障**：登录请求报 `429 rate_limited` 属正常限流（后台登录 10 次/分/IP）；若浏览器提示 `No 'Access-Control-Allow-Origin' header`，确认 API 的 CORS 中间件注册顺序（CORS 必须位于限流中间件外层，2026-08 已修复），且 `CORS_ORIGINS` 包含后台域名。