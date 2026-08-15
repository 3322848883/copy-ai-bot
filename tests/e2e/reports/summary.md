# 「信号聚合AI」本地全面生产级测试报告

**测试时间**：2026-08-13
**测试环境**：本地 Docker 全栈（APP_ENV=prod、SCRAPER_REAL=1、headful+xvfb、signal_session 持久化会话）
**测试方式**：API 自动化（pytest + httpx）+ 前端 E2E（Playwright）

## 结论

**API 自动化 75/75 通过，前端 E2E 6/6 通过，全链路验证成功。**

## 一、API 自动化测试（pytest，75 用例）

覆盖从注册开始的完整业务闭环，共 11 个 stage：

| Stage | 覆盖 | 关键断言 |
|---|---|---|
| 00 环境检查 | healthz / openapi / web / mailhog | 全部可达 |
| 01 数据准备 | 清限流 / purge 邮件 / 预插 Trader+画像 | 幂等 |
| 02 注册激活 | 3 用户注册→读码→验证→登录→风险揭示 | 重复注册 409、错码 4xx、未验证登录拒绝 |
| 03 身份 | 选所 / 好友码 / G27 交易所码 | 重复选所 409、自邀 409、错所码 4xx |
| 04 API Key | 列表不泄密钥 / prod 假 key 拒绝 | 白名单字段校验 |
| 05 策略 | admin force 上架(G04 留痕) / 公开列表 / 灰度 | listed + audit |
| 06 订阅支付 | 建单 → TxHash 负路径(failed) → DB 置 manual → admin 确认 → 订阅激活 | 限购 409、10% 邀请奖励 |
| 07 跟单 | 无订阅/跨所/Key 错配拦截 → paper 正路径 → 状态切换 | 同策略 409 |
| 08 提现 | 门槛/地址/超额负路径 → 10U 正路径 → approve/fill-tx | 余额锁定、状态机 |
| 09 后台 | admin RBAC / 用户冻结 / 支付单 / 邀请码 / 审计 | 403 隔离、audit 留痕 |
| 10 信号链路 | Redis 基线 / source_signals / 会话搜索 | 24264 命中 |

## 二、前端 E2E（Playwright，6 用例）

| Spec | 页面 | 验证 |
|---|---|---|
| 01 注册激活→登录 | /register /login | 完整 UI 注册 + mailhog 读码 + 风险弹窗 |
| 02 风险揭示→策略 | /login /strategies /strategies/[id] | 弹窗、E2E 策略可见 |
| 03 订阅页 | /subscriptions | 建单 + TxHash 负路径展示 |
| 04 我的跟单 | /bots | 卡片/模拟盘徽标/暂停恢复 |
| 05 提现页 | /withdraw | 地址正则校验与按钮联动 |
| 06 后台管理 | /admin/* | 登录/用户/支付/提现/信号页 |

## 三、测试发现并修复的问题

| # | 问题 | 严重度 | 修复 |
|---|---|---|---|
| 1 | 限流中间件对 CORS 预检 OPTIONS 也计数，导致真实请求+预检双倍消耗额度、预检 429 让浏览器 "Failed to fetch" | 高（生产安全） | `middleware.py` OPTIONS 直接放行 |
| 2 | `CopyBot.list` 序列化漏 `paper` 字段，前端模拟盘徽标不显示 | 中 | bots service 补 `"paper": bot.paper` |
| 3 | prod 模式注册验证码走 SMTP，compose 无 mailhog → 注册 500 | 高 | compose 加 mailhog 服务 + SMTP_HOST |
| 4 | `xvfb-run` wait+SIGUSR1 机制在容器 PID1 卡死，业务命令不执行 | 高 | entrypoint 显式后台启动 Xvfb |
| 5 | 容器重建后 user_data_dir 残留 SingletonLock 导致 signal_session 崩溃 | 高 | entrypoint 启动时清理 `Singleton*` |
| 6 | requirements 缺 psycopg2，alembic 迁移失败 | 高 | 补 `psycopg2-binary` |
| 7 | mailhog v1 API 返回数组（非 {items}），验证码 base64 需解码 | 中 | helper 双解码 + 数组兼容 |

## 四、产物

```
tests/e2e/
├── api/                # pytest 套件（conftest + helpers + 11 个 stage）
├── web/                # Playwright 套件（config + global-setup + 6 spec）
├── state.json          # 阶段间共享状态
├── cleanup.py          # 测试数据清理（保留 admin）
└── reports/
    ├── junit.xml       # pytest 报告（75 passed）
    └── playwright-report/  # E2E 报告（6 passed）
```

## 五、复跑方式

```powershell
# 1. API 自动化（宿主 .venv）
cd 'c:\Users\w6485\Desktop\AI 量化\信号聚合AI\tests\e2e'
& '..\..\..\.venv\Scripts\python.exe' -m pytest api -v

# 2. 前端 E2E
$env:PATH = 'C:\Program Files\nodejs;' + $env:PATH
cd web; npx playwright test

# 3. 清理测试数据
& '..\..\..\.venv\Scripts\python.exe' cleanup.py
```

## 六、遗留说明

- 支付真实链上 RPC 未接入（prod 链客户端 NotImplementedError），按计划用 admin 手动确认模拟到账；`submit_tx` 负路径作为预期断言。
- API Key 绑定在 prod 走真实交易所签名校验，测试用 DB 直插 key 记录验证归属/错配逻辑，绑定接口用 gate 假 key 验证拒绝路径。
- 提现余额由测试预插 available Reward 模拟成熟邀请奖励（真实 verifying 24/48h 不等待）。
- 信号基线 Redis 键依赖真实带单员活跃抓取，存在则校验新鲜度，不存在不强制失败（worker 心跳由任务结果保证）。
