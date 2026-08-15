# Celery 真实全链路验证报告与修复记录

> 日期：2026-08-13
> 目的：启动真实 Celery worker + beat，验证「Gate 带单广场实时信号 → 差分 → 信号入库 → 跟单执行」全链路
> 环境：Windows + 信号聚合AI 项目（Playwright 抓 Gate 带单广场，dev 模式，Redis 6380 / PG 5432）

## 验证结论速览

| 环节 | 状态 | 实测证据 |
|------|------|---------|
| 真实信号源爬取 | ✅ | 带单员枫1008（30809，996 粉丝）被 1 秒轮询 |
| 增量差分引擎 | ✅ | Redis 基线 `gate:feed:state:30809` 实时更新（age 0.4s，4 持仓） |
| 信号标准化入库 | ✅ | 差分 → `SourceSignal`（source_mode=A）持续写入 |
| 跟单执行层 | ✅ | `CopyEngine` → `CopyOrder`，bot #40（gate/10x/isolated/真实盘） |
| `signal.poll_live` | ✅ | 单次 60s 连续轮询 `rounds=44, events=0`，无错误 |
| `signal.reconcile` | ✅ | 与 poll_live 并发执行成功（`reconciled 1 leaders`） |
| `payment.poll_sweep` | ✅ | 正常返回 `no polling orders` |
| `reward.scan_verifying` | ✅ | 正常返回，无报错 |

**结论：全链路已贯通，1 秒级实时信号检测可用。**

---

## 修复记录（验证中定位并修复的 5 个问题）

### 0. qty 换算与测试符号过滤（★ 代码落地）

验证发现两项遗留问题，已在代码中落地实现：

- **qty 换算 0.0 → 有效数量**：新增 `SourceSignal.percent` 列（Alembic 迁移 `b2c3d4e5f607`）承载
  带单员持仓占比；`CopyEngine._effective_percent()` 按 `percent × 保证金` 缩放下单比例
  （open 动作 `bot.percent × leader_percent`，截断到 [0,1]；批量/WS 无占比时回退 `bot.percent`）。
- **TESTUSDT 过滤**：Gate 适配器 `fetch_live_positions` / `fetch_trader_positions` 与 Celery 任务层
  （`_poll_live_round` / `_reconcile_once`）双重过滤，symbol 含 `signal_test_symbols`
  （默认 `TEST/DEMO/FAKE`）即丢弃。配置项 `signal_test_symbols` 可调节。

修复合入点：`api/core/config.py`、`api/models/signal.py`、`api/services/scraper/adapters/gate.py`、
`api/services/copyengine/service.py`、`api/workers/tasks_signal.py`、迁移 `b2c3d4e5f607`。
单元测试：`api/tests/unit/test_copyengine_sizing.py`（7 例，全通过）。

### 1. Broker 端口错配（关键，导致任务发不到 worker）

- **现象**：`signal.reconcile` 等任务 `celery call` 后日志无接收记录，worker 无响应。
- **根因**：`api/core/config.py` 默认 `REDIS_URL=redis://localhost:6379/0`，而项目 `.env` 覆盖为
  `redis://localhost:6380/0`（6380 为映射端口，避开与 copy-ai-bot 的 6379 冲突）。
  - worker / beat 从**项目目录**启动时才能加载 `.env`，连到 **6380**；
  - 从其他目录执行 `celery call` 时未加载 `.env`，任务被发到 **6379**（无 worker 监听）。
- **修复**：所有 celery 命令（worker / beat / call）必须**在项目根目录
  `c:\Users\w6485\Desktop\AI 量化\信号聚合AI` 下执行**，并同时设置 `PYTHONPATH` 指向项目根。

### 2. `payment.poll_sweep` NameError

- **现象**：`NameError: name '_sweep_async' is not defined`。
- **根因**：`api/workers/tasks_payment.py` 中 `poll_payment_sweep()` 调用了不存在的 `_sweep_async()`，
  实际函数名为 `poll_payment_sweep_async`。
- **修复**：
  ```python
  return asyncio.run(poll_payment_sweep_async())
  ```

### 3. `reward.scan_verifying` NameError

- **现象**：`NameError: name '_scan_async' is not defined`。
- **根因**：`api/workers/tasks_reward.py` 中 `_run_scan()` 调用了不存在的 `_scan_async()`，
  实际函数名为 `scan_verifying_rewards_async`。
- **修复**：
  ```python
  return asyncio.run(scan_verifying_rewards_async())
  ```

### 4. `signal.reconcile` 事件循环崩溃（Event loop is closed / NoneType send）

- **现象**：reconcile 报 `RuntimeError: Event loop is closed` 与
  `AttributeError: 'NoneType' object has no attribute 'send'`。
- **根因**：多个 Celery 任务各自调用 `asyncio.run()` 新建独立事件循环，却共享 `api/db/session.py`
  的模块级**单例异步引擎连接池**。连接池中在旧循环创建的 asyncpg 连接，被新循环复用时报错。
- **修复（两层）**：
  - `api/db/session.py`：异步引擎改用 **`NullPool`**（连接按需创建、用完即弃，彻底消除跨循环复用）。
    ```python
    from sqlalchemy.pool import NullPool
    _engine = create_async_engine(
        settings.database_url, echo=settings.debug,
        pool_pre_ping=True, poolclass=NullPool,
    )
    ```
  - `api/workers/tasks_signal.py`：在 `_poll_live_loop` 与 `_reconcile_once` 的 `finally` 中
    释放引擎池，兜底清理残留连接。
    ```python
    finally:
        await scraper.close()
        from api.db.session import get_engine
        await get_engine().dispose()
    ```

### 5. Solo 池导致任务饿死

- **现象**：`poll_live` 是 60 秒连续任务，被 beat 每 60 秒重踢，长期独占 worker；
  `reconcile` / `payment` / `reward` 队列被饿死，迟迟不执行。
- **根因**：worker 使用 `--pool=solo`（串行，同一时刻只执行一个任务）。
- **修复**：改用线程池并发执行异步任务。
  ```
  celery -A api.workers.celery_app:celery_app worker --pool=threads --concurrency=4
  ```

### 6. 页面池并发：一浏览器监控多带单员（★ 代码落地 + 实机验证）

**背景**：同一交易所很多带单员时，原实现是单页面串行 `for` 循环拉取，单轮耗时 =
「交易员数 × 单次往返」，规模上来会跟不上合约交易。浏览器定**身份**（指纹+cookie）而非并发上限，
并发靠同一 context 内的多个页面（共享会话）实现。

**改造**（把串行改为页面池并发）：

- 配置项 `scraper_page_pool_size`（默认 `4`）：同一浏览器内并行页面数 = 并发上限。
- `GateScraper`：`_ensure_browser` 在同一 context 下并行开 N 页（共享同一指纹/cookie）；
  `_api` 支持指定 page（该页独立 fetch，多页互不阻塞），不传时 round-robin 分配；
  新增 `fetch_live_positions_many(trader_ids)`，用 `asyncio.Semaphore` 限流 + `asyncio.gather`
  并发拉取多个带单员持仓快照。
- `IncrementalFeedService`：新增 `poll_leaders_many` / `reconcile_leaders_many`，一次并发拉取
  全部持仓再逐个差分（避免串行 N×往返）；抽 `_poll_with_snapshot` 复用存取逻辑。
- `tasks_signal.py`：`_poll_live_round` 改用 `poll_leaders_many`，`_reconcile_once` 改用
  `reconcile_leaders_many`；抽公用 `_handle_events` 统一落库 + 交 CopyEngine。

**效果**：单轮耗时从「交易员数 × 单次往返」降到「(交易员数 / 池大小) × 单次往返」。
例：50 带单员、500ms 往返、池=4 → 串行约 25s，并发约 6.25s。

**单元测试**：`api/tests/unit/test_signalfeed.py` 新增 3 例（批量差分、部分失败跳过、批量对账），
共 22 例全通过。

修复合入点：`api/core/config.py`、`api/services/scraper/adapters/gate.py`、
`api/services/signalfeed/service.py`、`api/workers/tasks_signal.py`。

**实机验证记录**（2026-08-13 重启 worker/beat 后）：
- 新代码 04:29:21 接管，浏览器以 `headless=False mode=new` 启动（匹配 `.env`）。
- 首个 poll_live `e7c7b998` 成功：`rounds=35, events=0`（建基线），无接口失败。
- Chrome 13 进程（主+GPU+网络+多渲染进程），与页面池开 4 页一致。
- 说明：当前仅 1 个活跃带单员，`fetch_live_positions_many` 只拉 1 个交易员，批量路径已生效，
  但多页面并行的真实提速需多带单员时才能观察到（代码路径已确认正常）。

### 7. 模式2 归属修复：leader_id 必须取数据行顶层（★ 真实报文校准 + 实机验证）

**问题**：用户反馈「跟单模式只能监控自己仓位并对应好带单员；很多带单员隐藏仓位信息，监控没用」。
模式2 的正确语义是**只监控「自己已跟单」的镜像仓位**（`/apiw/v2/copy/follower/position`），
带单员隐藏公开仓位不影响镜像仓位（始终可见、方向真实）。但修复前解析存在致命 bug：

**根因**（★ 2026-08 真实报文校准）：
- 原 `_parse_follower_positions` 从 `trader_info.leader_id` 取归属，但真实报文里
  `leader_id` 在**数据行顶层** `row["leader_id"]`（int，如 `32801`），`trader_info` 只有
  `nick/nickname/anonymous`。取错 → 归属为空字符串 → 无法按带单员隔离，
  会把跟单账户里其他带单员的仓位误标为空归属（带单员隐藏仓位时尤为致命）。
- 字段口径其他修正：`qty` 取 `row["qty"]`（跟单数量 `"0.001"`），不是 `size`（`"0.1"` 是张数）；
  `leverage` 跟单接口恒为 `"0"`，回退 `cross_leverage_limit`（真实最大杠杆）；`market` 去下划线。

**修复**：`GateScraper._parse_follower_positions` 改为取顶层 `row["leader_id"]`（兜底 `trader_info`），
`qty`/`leverage` 口径修正。`fetch_follower_positions_many` 按顶层 leader_id 分组隔离，
`IncrementalFeedService.poll_followers_many` 按 leader_id 独立建基线与差分，绝不可混淆。

**配置**：`.env` 增加 `SIGNAL_FOLLOWER_LEADER_IDS=["32801"]`（JSON 数组格式，pydantic tuple 需 JSON 解码）
与 `SIGNAL_SESSION_ENABLED=true`。任务层 `_poll_live_round` 按
`leader_id ∈ signal_follower_leader_ids` 路由：模式2 走 follower 差分，否则走模式1 公开广场。

**单元测试**：`api/tests/unit/test_signalfeed.py` 新增 3 例（顶层 leader_id 归属、多带单员隔离、
测试符号过滤），共 15 例全通过。

**实机验证记录**（2026-08-13，真实跟单账号 + 持久化登录会话）：
- 登录后 `fetch_follower_positions_many(['32801'])` → `leader_id=32801` 正确隔离 1 个持仓：
  `ETHUSDT short qty=0.001 lev=50`（复利如慢牛，leader_id 顶层=32801）。
- 差分引擎首轮正确建基线 `{'32801': 0}`（存量持仓不产出信号，符合设计）。
- ★ 空仓交易员不漏跟单：实测用户跟单了两个交易员但仓位只有一个——另一交易员当前空仓，
  `follower/position` 不返回空仓行。通过 `/api/copytrade/copy_trading/follow/order` 自动发现：
  当前运行中跟单 = `32801`（复利如慢牛，有仓）+ `24264`（风懃，空仓）。新增
  `fetch_followed_leaders()` 自动发现全部已跟单交易员（含空仓），任务层 `_poll_live_round`
  动态合并进模式2 监控，避免手动维护 `signal_follower_leader_ids` 漏掉新跟单交易员。
- 端到端：自动发现 2 个 → 对 `24264`（空仓）正确建空基线、`32801` 事件数=0，无异常。

修复合入点：`api/services/scraper/adapters/gate.py`、`api/core/config.py`、`.env`、
`api/workers/tasks_signal.py`、`api/tests/unit/test_signalfeed.py`。

---

## 标准启动命令（必须在项目根目录执行）

```powershell
cd 'c:\Users\w6485\Desktop\AI 量化\信号聚合AI'
$env:PYTHONPATH = 'c:\Users\w6485\Desktop\AI 量化\信号聚合AI'

# worker（线程池，4 并发）
& 'c:\Users\w6485\Desktop\AI 量化\信号聚合AI\.venv\Scripts\celery.exe' `
  -A api.workers.celery_app:celery_app worker --pool=threads --concurrency=4 --loglevel=info

# beat（调度器）
& 'c:\Users\w6485\Desktop\AI 量化\信号聚合AI\.venv\Scripts\celery.exe' `
  -A api.workers.celery_app:celery_app beat --loglevel=info

# 手动触发单任务（须与 worker 同一 broker，即同一 cwd）
& 'c:\Users\w6485\Desktop\AI 量化\信号聚合AI\.venv\Scripts\celery.exe' `
  -A api.workers.celery_app:celery_app call signal.reconcile
```

---

## 遗留待办 / 注意事项

- [x] **信号 `qty` 恒为 0.0**：已落地 `percent × 保证金` 换算（`CopyEngine._effective_percent`），
  信号新增 `percent` 列承载带单员占比，open 动作据此缩放下单比例。
- [x] **测试符号混入**：已落地 `TESTUSDT` 过滤（Gate 适配器 + Celery 任务双层过滤，
  配置项 `signal_test_symbols` 默认 `TEST/DEMO/FAKE`）。
- [ ] **信号重复 open**：同一 `ETHUSDT` 在 30 秒内多次触发 `open`。可能为带单员持仓占比围绕阈值
  （`signal_change_threshold=0.005`）波动导致，需观察是否为真实交易还是差分抖动。
- [ ] **首次仅建基线**：`poll_leader` 首次无基线时只建基线、不产出信号（存量持仓不执行），
  符合「只跟新开仓/新平仓」设计，属预期行为。
- [ ] **日志噪音**：`debug=True` 使 SQLAlchemy engine echo 打到 INFO，轮询日志非常冗长，
  生产建议关闭 `debug` 或调低日志级别。

---

## 模式2 信号源：跟单账户持仓监控（★ 代码落地 + 实机验证）

**背景**：用户以自己的小号作为信号源（模式2），在小号上跟单交易员「复利如慢牛」（10U）。
信号源需监控**跟单账户**的镜像持仓——因为标准合约接口 `/futures/usdt/positions` 返回 size=0
（跟单持仓在独立跟单子账户），Gate v4 标准 API 也没有跟单持仓接口，故必须走浏览器登录会话抓取。

**实机验证**（2026-08-13，浏览器登录 A寒風 会话）：
- 跟单关系确认：复利如慢牛（leader_id=32801），跟单金额 10U，可用 9U，开始 04:51:23。
- 当前镜像持仓：ETH_USDT 空单，开仓价 1886.04，qty 0.001，全仓 50X。
- 核心接口 `GET /apiw/v2/copy/follower/position?trader_name=&market=&page=&page_size=&sub_website_id=0`
  返回 `code=200`，含 `market`/`side`/`qty`/`entry_price`/`trader_info.nick`/`leader_id`。
  带 `trader_name=复利如慢牛` 过滤同样可用（实测两次返回同一持仓）。

**代码落地**：`api/services/scraper/adapters/gate.py` 新增模式2信号源方法：
- 常量 `FOLLOWER_POSITION_PATH = "/apiw/v2/copy/follower/position"`。
- `fetch_follower_positions(trader_name="")` → `list[RawPosition]`：空=全部跟单持仓，指定=该交易员。
  `market` 归一化（`ETH_USDT`→`ETHUSDT`）、方向真实（long/short）、qty/entry 解析、测试符号过滤。
- `fetch_follower_positions_many(trader_names)` → `{trader_name: [RawPosition]}`：★页面池并发，
  每个 trader_name 一个请求落到不同 page 互不阻塞，语义与 `fetch_live_positions_many` 一致。
- `_parse_follower_positions` 静态解析器 + `_mock_follower_positions` dev 降级。

**parser 单测（真实返回样本）**：`ETH_USDT/short/qty0.001/entry1886.04/leader32801` 解析正确；
`TEST_USDT` 被 `signal_test_symbols` 过滤，`BTC_USDT` 保留。

**鉴权实测（★关键结论）**：`/apiw/` 前缀接口**不能用 API Key 签名调用**。
- 用 Gate v4 签名（KEY/Timestamp/SIGN）GET `/apiw/v2/copy/follower/position` 与 `/apiw/v2/copy/leader/abstract` → 均返回 `HTTP 403`。
- 根因：`/apiw/` 是 Gate **网页内部接口**，用**浏览器登录 cookie 会话**鉴权，不走 API Key；
  官方 `KEY/SIGN` 签名仅用于 `/api/v4/` 前缀的标准接口。
- 结论：模式2信号源**必须依赖已登录的浏览器会话**（Playwright fetch 时携带 cookie），
  无法用纯 API Key 获取跟单持仓。自动化方案 = Playwright 持久化上下文（`user_data_dir`）首次手动登录一次，
  之后程序化复用 cookie 会话；无头模式需页面内 fetch 携带指纹（Akamai 拦截纯 headless 导航）。

### 后台管理「登录 Gate」功能（★ 代码落地）

**需求**：项目部署在服务器并绑定域名后，需从任何设备访问后台管理，在后台管理里直接选择模式2并完成登录。

**关键认知**：登录的 cookie 必须落在**服务器端**（信号源由服务器调用 `/apiw/`），用户本地浏览器登录拿不到。故采用**远程浏览器串流**——后台管理页面内嵌服务器端浏览器实时画面，用户在页面里直接操作它完成登录（含验证码/滑块），登录态写入 `user_data_dir` 持久化。

**实现**：
- `api/services/signal_session/service.py`：`SignalSession` 单例，`launch_persistent_context(user_data_dir)` 持久化会话；
  截图推送 `screenshot()`、输入事件转发 `dispatch_event()`（click/mousemove/wheel/type/press/navigate）、
  登录校验 `complete_login()`（页面内 fetch 跟单接口判 code=200）。
- `api/routers/admin/signal_session.py`：`/status` `/start` `/screenshot` `/event` `/complete` `/close`（aud=admin）。
- `web-ui/app/admin/signal-session/page.tsx`：后台管理「信号源登录」页，内嵌远程浏览器视图（截图轮询 + 鼠标/键盘事件转发）。
- `api/services/scraper/adapters/gate.py` `_ensure_browser`：`signal_session_enabled` 时改用持久化上下文（复用后台登录会话，同一 `user_data_dir`）。

**配置**：`config.yaml` 新增 `signal_session_enabled: true`（结算启用）、`signal_session_data_dir`、`signal_session_headless`。

**并发约束**：`user_data_dir` 被 Playwright 锁定，后台登录会话开着时信号源复用其上下文，不重复 launch；两者勿并发各自启动同一目录。

**后续接入点**：`IncrementalFeedService` 需新增模式2差分（按 `trader_name` 为 key、`{symbol: qty}` 快照），
`tasks_signal.py` 需按模式配置路由到 follower 或 leader 接口。留待模式2全链路接入时落地。

### 8. 后台「搜索带单员」功能（★ 2026-08 新增，只展示不跟单）

**需求**：后台按昵称/ID 搜索 Gate 带单员画像，用于人工确认要跟单的对象。仅搜索展示，不触发跟单/下单。

**Gate 接口能力（★ 2026-08 真实会话实测）**：
- 按昵称搜索：`/apiw/v2/copy/leader/search?name=<kw>`（★ 参数名是 `name`，非 `keyword`；返回模糊匹配列表）
- 按 ID 查详情：`/api/copytrade/copy_trading/trader/detail/{leader_id}`（返回完整交易画像）
- 注意：`leader/search` 只按昵称匹配；纯数字 ID 不匹配昵称返回空，需用 detail 接口反向确认。

**实现**：
- `api/services/scraper/adapters/gate.py`：新增 `search_leaders(keyword,page,page_size)`（复用已登录持久化会话走 `_api`），
  `_to_pct` 把接口小数比例转百分比；新增常量 `LEADER_SEARCH_PATH`。
- `api/routers/admin/signal_session.py`：新增 `GET /search?keyword=`（aud=admin），复用 `GateScraper.search_leaders`。
- `web-ui/app/admin/signals/page.tsx`：信号源管理页新增「搜索带单员」卡片（输入昵称 → 展示 leader_id/昵称/收益/胜率/回撤/跟单人数/已跟单状态）。

**单元测试**：`api/tests/unit/test_signalfeed.py` 新增 2 例（按昵称解析画像、空关键字返回空），共 18 例全通过。

**实机验证记录**（2026-08-13，真实登录会话）：
- 搜「风懃」→ `24264`（风懃，is_follow=True）+ `16708`（风懃888）
- 搜「复利如慢牛」→ `32801`（is_follow=True）
- 搜「三」→ 模糊匹配多个（一剑三仟/农夫三十拳/三年之期已到等），含 roi30/胜率/回撤/跟单人数画像。

修复合入点：`api/services/scraper/adapters/gate.py`、`api/routers/admin/signal_session.py`、
`web-ui/app/admin/signals/page.tsx`、`api/tests/unit/test_signalfeed.py`。

### 8.1 按 ID 精确查兜底（★ 2026-08 新增）

**需求**：`leader/search` 只按昵称匹配，纯数字 ID 返回空。补充按 ID 精确查入口。

**实现**：
- `gate.py`：新增 `get_leader_by_id(leader_id)`，走 `/api/copytrade/copy_trading/trader/detail/{id}`，
  解析 `config`（style/abstract/markets/跟单区间）+ `profit`（roi/胜率/回撤/跟单人数）。
  非纯数字 ID 直接返回 None。markets 截断前 15 个（detail 返回全部历史标的多达 600+）。
  detail 接口不返回昵称，nick 用 `Leader{id}` 占位。
- `signal_session.py`：`/search` 端点对 `keyword.isdigit()` 走 `get_leader_by_id`，返回 `source:"detail"`。
- `signals/page.tsx`：detail 结果在表格下方展示风格/跟单区间/简介/交易标的画像区。

**单元测试**：新增 2 例（detail 画像解析、非数字 ID 拒绝），共 20 例全通过。

**实机验证记录**（2026-08-13）：
- 按 ID 查 `24264` → style=high-frequence|preserve|short-line，roi30=-64.42%，胜率 40.1%，跟单区间 10~50000 USDT
- 按 ID 查 `32801` → style=long-line|high-frequence|radical，roi30=0.25%，交易标的多达 620 个（截断前 15）

修复合入点：`api/services/scraper/adapters/gate.py`、`api/routers/admin/signal_session.py`、
`api/tests/unit/test_signalfeed.py`。

## 关键配置项（config.yaml 对应 `api/core/config.py`）

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `signal_poll_interval` | 1 | 轮询间隔（秒） |
| `signal_poll_loop_seconds` | 60 | 单次任务连续运行时长（秒），到点交还 beat 重踢 |
| `signal_change_threshold` | 0.005 | 持仓占比阈值，低于视为噪音过滤（0.5%） |
| `signal_reconcile_interval` | 600 | 全量对账间隔（秒），强制重同步基线防漂移 |
| `signal_test_symbols` | `TEST/DEMO/FAKE` | 测试符号标记，symbol 命中即丢弃 |
| `scraper_headless` | None | 无头可配置；None=自动(prod 默认无头)，True/False 强制。实测 Gate 无头被 Akamai 拦截，需 `SCRAPER_HEADLESS=false` + xvfb 有头 |
| `scraper_headless_mode` | `new` | 无头模式：`new`(现代,指纹难区分) / `old`(旧,易被检测) |
| `scraper_page_pool_size` | 4 | 页面池并发：同一浏览器内并行页面数 = 并发上限 |