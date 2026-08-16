# 后台功能核查与假操作按钮修复记录

> **日期**：2026-08-16
> **范围**：后台（web-admin）前台有界面但后台无对应接口/配置的功能逐板块核查，并修复"假操作"按钮（仅弹 toast、无真实后端调用）。
> **关联文档**：`2026-08-12-signal-saas-design-gap-analysis.md`（设计与需求差异）

---

## 一、本次处理的问题清单

| 板块 | 前端位置 | 问题 | 修复方式 |
|------|---------|------|---------|
| 风险中心 | 策略级风控「编辑」 | 按钮仅弹 toast，无接口调用 | 新增 `GET/PATCH /admin/v1/signals/{id}/risk`（Redis `risk:strategy:*`，audit 留痕）+ 前端编辑弹窗 |
| 风险中心 | 高危用户「复核 / 解除」 | 按钮无真实操作 | 前端改调已有的 `PATCH /admin/v1/users/{id}/freeze`（冻结/解冻 + audit） |
| 信号源 | 「同步画像」 | 按钮仅弹 toast | 新增 `POST /admin/v1/signals/sync`：单带单员同步执行 / 全量投递 Celery `profile.sync_daily`；新增 `tasks_profile.run_sync_one_sync` |
| 数据概览 | 「导出报表」 | 按钮无导出行为 | 前端收集当前数据生成 CSV 下载（含注册量/支付额/跟单数/提现/风控/邀请等） |
| 用户管理 | 详情抽屉「财务 / 跟单 / 交易所」占位 | 后端未聚合返回，前端显示 "—" | 扩展 `GET /admin/v1/users/{id}` 返回 `financial`（5 字段）/`copy`（运行机器人/今日/本周）/`exchange` |
| 用户管理 | 详情抽屉「备注」 | 按钮仅弹 toast | 新增 `users.admin_note` 字段（迁移 `f5a6b7c8d9e0`）+ `PATCH /admin/v1/users/{id}/note`（audit `user.note_update`）+ 前端可编辑/保存 |

> 以上均端到端验证通过（接口 200、写操作 audit 留痕、前端生产构建 TypeScript 校验通过）。

---

## 二、验证码开关（`verify_code_enabled`）真正生效

**问题**：后台设置页已有 `verify_code_enabled` 开关、后端 `/settings/rules` 可读写，但 `AuthService._code_enabled()` **从未被调用**——注册无论如何都发验证码、用户必须验证后才激活，开关是"死配置"。

**修复**：
- `register()`：开关开启 → 照常发验证码、`is_active=False`；开关关闭 → **注册即激活**（`is_active=True`），不发送验证码。
- `verify_email()`：开关关闭时，历史未激活用户直接激活。

**验证**（端到端）：
- 关闭：注册 → `is_active=True`，登录 200 成功。
- 开启：注册 → 需验证，登录 401 要求验证。

---

## 三、邮件发送与模板

### 3.1 邮件总开关（`mail_enabled`）
- 新增平台参数 `mail_enabled`（后台「系统设置 · 邮件」）。
- `Mailer._dispatch`：`mail_enabled=False` 时仅 dev 控制台兜底；开启则走 SMTP。
- 邮件始终走 SMTP（`smtplib`），不再因 `app_env == "dev"` 一律退化为控制台输出。

### 3.2 模板渲染健壮性
- 渲染由 `str.format()` 改为 `_wrap()` 占位符替换（`{code}`/`{ttl}`/`{name}`/`{expires}`），避免后台模板含 CSS 花括号时抛异常；外层容器由 `_wrap` 统一提供。

### 3.3 默认模板完善
- 邮箱验证码模板：品牌 header + 大号验证码卡片 + 有效期/防泄露提示 + footer。
- 订阅临期提醒模板：品牌 header + 到期提醒 + 到期影响说明 + 续费引导 + footer。
- 已清理 Redis 中残留的旧测试模板（`{"subject":"测试主题","html":"<p>{code}</p>"}`）。

### 3.4 SMTP 配置（待生产接入）
真实 SMTP 发送留待生产模式配置后测试。接入时需：
1. 在 `.env` 配置 `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `MAIL_FROM`。
2. 后台开启 `mail_enabled = True`。
3. 用注册流程实测验证码邮件送达。

---

## 四、运行环境备注

- 本地生产测试库：postgres 监听 **5433**（`docker-compose.prod.local.yml` 映射 5433:5432），user=`signal`，password=`local-test-pg-pass-2026`，库 `signal_saas`；Redis 用 **6381**。
- 运行 API/迁移须设 `DATABASE_URL=postgresql+asyncpg://signal:local-test-pg-pass-2026@localhost:5433/signal_saas`（`.env` 默认 5432 未监听）。
- web-admin 前端连 API **8000**（`.env.local` 的 `NEXT_PUBLIC_API_BASE`），前端为生产构建（`npm run build` 后 `next start -p 3001`）。

---

## 五、设置页客户端异常 + "空白页面" 修复（同日补记）

### 5.1 设置页 `Application error: a client-side exception`
- **表象**：后台「系统设置」页报 `ChunkLoadError: Loading chunk 662 failed (.../app/settings/page-*.js)`。
- **根因**：非代码缺陷，而是**陈旧构建不一致**——`npm run build` 重新生成 chunk 哈希后，运行中的 `next start` 仍向浏览器下发引用**旧 chunk 哈希**的 HTML，浏览器拉取旧 chunk 404，触发 Next.js 错误边界。
- **修复**：停掉 3001 前端 → `npm run build` 重建 → 以 `next start -p 3001` 重启。验证服务端 HTML 引用的 chunk 与磁盘 `.next/static/chunks/app/settings/page-*.js` 完全一致。
- **用户侧**：若仍见旧错误，浏览器硬刷新（Ctrl+F5）即可。

### 5.2 "好多空白页面" —— CORS 白名单未含前端端口
- **表象**：后台多个页面空白/被迫跳登录。
- **根因**：运行中的 API 以部分配置启动——DB/Redis 用 prod-local（5433/6381）正确，但 **CORS 白名单未含前端端口 3001/3002**（落到默认 3000），浏览器 CORS 预检被拒，所有 `/admin/v1/*` 请求被浏览器拦截，页面拿不到数据 → 空白。
- **修复**：以完整 prod-local 环境重启 API：`.\scripts\set-prod-local-env.ps1`（内含 `CORS_ORIGINS=http://127.0.0.1:3001,3002,localhost:3001,3002` + `CORS_ALLOW_LOCAL_TEST=1`）后再 `uvicorn api.main:app --port 8000`。预检验证 3001/3002 均返回 200 且回显 `Access-Control-Allow-Origin`。

### 5.3 启动 API 必须用 prod-local 环境（重要）
- `.env`（dev）的 `DATABASE_URL=...:5432`、`REDIS_URL=...:6380` **均未监听**；实际容器为 **PG 5433**（口令 `local-test-pg-pass-2026`）、**Redis 6381**。
- 直接 `uvicorn api.main:app` 会因连不上 Redis/PG 而 500（登录接口表现为 Internal Server Error）。
- **正确启动方式**：先 `. .\scripts\set-prod-local-env.ps1` 设置环境变量，再启动 API / worker / beat / consumer。
- 本轮已把闲置的 API 统一重启为 prod-local 环境；`.env`（dev）保持原样未改动。

### 5.4 验证结果
- Playwright 无头注入 admin token 遍历 14 个后台页面：全部 `200 + 有正文 + 无 ChunkLoad/CORS/网络错误`。
- 设置页聚焦检查：平台参数（注册邮箱验证码/邀请奖励/链上确认/支付订单/邮件）、邮件模板（验证码/订阅临期）、订阅套餐（试用/正式）**全部渲染出真实数据**，控制台 0 错误。