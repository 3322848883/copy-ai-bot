# 上线全局核查修复记录（2026-08-19）

> 逐功能前台后台对照检查产出的修复全集。四批 commit：
> `fa82d81` 品牌重塑 OmniAlpha + 通知公告全链路 + 公开配置端点 →
> `91d6b30` P0×3 + P1×5 → `b31e139` 构建上下文瘦身 → `b3bf20f` P1/P2 收尾。

## 1. P0（资金安全）

| # | 问题 | 修复 |
|---|---|---|
| P0-1 | 用户已真实打款但交易未上链/RPC 故障时订单被误判 failed，形成资金死单 | `submit_tx` 重排三态分流：先查链上存在性，未上链/RPC 故障 → `verifying` 转轮询；`poll_order` 确认前补齐 to/value 校验（`_verify_value` 返回三态） |
| P0-2 | `seed_prod_admin.py` / `check_pending.py` 存在弱口令兜底默认值 | 删除默认值，强制环境变量注入，缺失即退出 |
| P0-3 | 提现链上校验下限按订单全额核对，与用户实际到账（扣除手续费后）矛盾 | 校验下限改净额 `amount - fee`，admin 界面同步提示按净额打款 |

## 2. P1（逻辑/一致性）

**支付与订单**
- 订单 TTL 内联校验：`submit_tx` 拒绝过期 pending 单（置 expired）；admin `manual_set` 放开 failed/expired 恢复通道；前端倒计时归零禁用提交。
- 人工确认支付（`admin/payments.py`）：`SELECT FOR UPDATE` 行锁 + 状态 CAS——并发双确认会双倍延期 + 双发奖励（真金白银），由数据库层挡住。
- confirmed 对账补偿任务 `payment.confirm_reconcile`（beat 注册）：`_confirm` 置 confirmed 后进程若在 `activate_subscription` 前崩溃，留下"钱到账但套餐未开通"死单；以 `subscription.payment_order_id` 为幂等键自动补偿。

**奖励与统计**
- 风控命中奖励以 frozen 状态落库（原直接丢弃），scan 任务同时释放 verifying/frozen。
- 邀请统计按 `Reward.status` 精确聚合（新增 frozen_reward/withdrawn_reward 字段），前端统计卡改用后端口径。

**跟单引擎**
- 虚拟锁定精算：平仓/减仓按仓位名义价值 ÷ 杠杆释放（原整 bot 清零/误走加仓分支）。
- 订阅闸门 fail-closed：DB 异常时返回 False 拦截开/加仓（原 fail-open）。
- 激活死规则修复：全局并发节流与当日亏损熔断字段此前恒为默认值，永不触发。

**信号链路**
- 差分互斥锁：`poll_live`（1s）与 `reconcile`（10min）并发差分同一 Redis 基线会双发同一开/平仓事件（双倍真实下单）；Redis `SET NX EX` 互斥，Redis 故障时退回无锁旧行为。

**后台管理**
- 审计筛选服务端化：`danger`（高危动作全集 `DANGER_ACTIONS`）/`action` 前缀/`actor_id` 全部走 SQL 过滤（原客户端过滤只作用于当前页）；actor 输入防抖 400ms。
- 用户管理：补分页（原只拉首屏 50 条）；正常/冻结筛选走服务端 `status` 参数。
- 订单 KPI「今日订单」改今日（UTC 0 点）口径（原统计全量）。
- 高危用户「冻结奖励」列按 `Reward.status='frozen'` 真实聚合（原恒 0 假数据）。

**配置安全**
- `APP_ENV` 默认值 dev → prod，非法值（staging 等）启动即报错：忘配环境时 fail-fast，杜绝静默落入 dev（mock 链客户端/固定验证码等测试后门生效）。

**前台体验**
- 新增 `web-ui/lib/time.ts`：统一本地时区格式化，修复 7 处 UTC 直显（订阅有效期、支付历史、邀请列表/图表、rewards 流水、首页订阅卡），北京时间不再差 8 小时。
- 跟单固定金额输入框（原硬编码 500）；maxNotional 改"风控上限"语义。
- 订阅页 APTOS_TX_RE 正则（0x 可选）+ 按链区分 placeholder + 教程文案同步。

## 3. P2（文案/死代码）

- withdraw 驳回原因为空时显示"管理员未注明（如有疑问请联系客服）"，不再编造"收款地址与实名不符"。
- account 页：API 卡假"已连接"改"已绑定"；删除 G27 内部码外露；删除"主号下级免订阅权益"假承诺。
- terms/privacy 移除"平台基础模板，正式上线前需外部法务复核"草稿声明外露。
- 策略管理页删除模式 B 静态假状态卡（"子账户 ID — / V2 待接入"），运维看板只保留真实模式 A 会话卡。
- v1 strategies 用户侧状态死接口删除。

## 4. 构建与部署

- 根 `.dockerignore` 补排除 `web-admin/node_modules`（~450MB）/ `web-admin/.next` / `tests`（81MB）：api/worker 构建上下文 525MB → KB 级，重建秒级。
- 全部六容器（api/worker/beat/consumer/web/web-admin）已用新镜像重建。

## 5. 验证记录（2026-08-19）

- 静态：`tsc --noEmit`（web-ui / web-admin）、eslint 改动文件、`compileall api` 全部通过。
- 冒烟：`/healthz` 200；用户登录 OK；`users?status=normal|frozen`、`orders/failures`（今日口径）、`risk/high-risk`、`audit?danger=true` 均正常；`/terms` `/privacy` 200。
- 四链解析此前已用真实链上数据验证（BEP20 67.39U 正确解析、97 确认数等，详见会话记录）；Aptos 完成端到端真实资金验证。

## 6. 遗留待办（人工操作）

- [ ] 后台「系统设置 → 客服联系」填 support_email / support_telegram。
- [ ] 「邮件」组 `mail_from` 改为实际发信域名。
- [ ] （建议）BEP20 1U 真实资金复验——本轮四链解析改动最多的链。
- [ ] 本地测试管理员（`admin@local.test`，验证用临时 seed）确认无用后删除。
