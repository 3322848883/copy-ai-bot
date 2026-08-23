# Gate 公开带单广场爬虫（M2 T2.1 真实采集实现 ★2026-08 逆向验证）
from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from api.core.config import get_settings

logger = logging.getLogger("signal-saas.scraper.gate")

# ★反爬(需求 §2.10)：每个带单员详情页随机间隔 3-8s
SCRAPE_MIN_INTERVAL_S = 3
SCRAPE_MAX_INTERVAL_S = 8

# Gate 真实数据接口（浏览器上下文内 fetch，携带完整指纹绕过 Akamai 风控）
GATE_BASE = "https://www.gate.com"
LEADER_LIST_PATH = "/apiw/v2/copy/leader/list"
# ★ 按昵称搜索带单员（★ 2026-08 实测：参数名是 name，非 keyword；返回模糊匹配列表）
LEADER_SEARCH_PATH = "/apiw/v2/copy/leader/search"
LEADER_DETAIL_PATH = "/api/copytrade/copy_trading/trader/detail/{leader_id}"
LEADER_POSITION_PATH = "/api/copytrade/copy_trading/trader/position_composition"
LEADER_TRADES_PATH = "/apiw/v2/copy/api/leader/trading_view"
# ★ 带单员实时持仓（2026-08-20 详情页抓包确认：含 side/entry_price/mark_price/unrealised_pnl/margin）。
#   区别于 position_composition（仅持仓占比统计）：这是当前真实仓位行，方向真实。
#   带单员隐藏持仓（config.is_hide=1）或当前空仓时 data=[]。
LEADER_LIVE_POSITION_PATH = "/api/copytrade/copy_trading/trader/position"
# ★ 带单员每日收益序列（2026-08-20 详情页抓包确认：网页收益走势图数据源，data_type=month 返回近30天）。
#   每行 profit_rate 为累计收益率小数（与 detail.simple_profit_rate 同口径），create_time 为当日时间戳。
LEADER_PROFIT_CHART_PATH = "/apiw/v2/copy/leader/profit_chart"
# ★ 带单员已平仓记录（2026-08-22 详情页"历史带单"抓包确认）：每行含真实方向
#   side(long/short)/已实现盈亏 profit/收益率 profit_rate/开平仓均价/时间——
#   区别于 trading_view（无方向无价格）：详情页交易记录的最佳数据源。
#   ★ 对隐藏持仓（is_hide）交易员同样完整返回（27714 实测 475 条，含 side=short 行）：
#     历史平仓记录不受 is_hide 屏蔽，是隐藏交易员公开可得的唯一带方向数据。
LEADER_CLOSED_POSITION_PATH = "/apiw/v2/copy/leader/close_position"
# ★ 模式2 信号源：跟单账户持仓（监控自己跟单的交易员镜像仓位，★需登录会话）
#   由「我的跟单」页 https://www.gate.com/zh/copytrading/mine?mode=futures&type=copy 调用。
#   区别于模式1 公开接口：返回的是已跟单交易员的镜像仓位，方向真实(long/short)、数量按跟单比例缩放。
FOLLOWER_POSITION_PATH = "/apiw/v2/copy/follower/position"
# ★ 模式2 信号源：已跟单交易员列表（★ 2026-08 实测：返回全部运行中的跟单，含空仓的 leader_id+昵称）。
#   空仓交易员在 position 接口不出现，只能靠此接口自动发现，避免手动维护 leader_id 配置。
FOLLOW_ORDER_PATH = "/api/copytrade/copy_trading/follow/order"


@dataclass
class RawTrader:
    """公开排行榜上的带单员原始记录。"""

    trader_id: str
    name: str
    followers: int = 0
    roi_7d: float = 0.0
    roi_30d: float = 0.0
    roi_90d: float = 0.0
    roi_all: float = 0.0
    win_rate_30d: float = 0.0
    win_rate_all: float = 0.0
    max_drawdown: float = 0.0
    trading_days: int = 0
    # ★ 带单员是否隐藏当前持仓（detail config.is_hide）：决定上架模式——
    #   公开仓位→模式A（公开广场采集跟单）；隐藏→模式B（绑定 API 镜像跟单）
    hide_position: bool | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class RawPosition:
    """带单员实时持仓（→ 信号源）。"""

    trader_id: str
    symbol: str
    side: str  # long / short
    leverage: int = 1
    qty: float = 0.0
    entry_price: float = 0.0
    opened_at: datetime | None = None
    raw: dict = field(default_factory=dict)


class GateScraper:
    """Gate.io 合约带单广场真实采集（Playwright 驱动）。

    数据链路（★ 2026-08 实测验证）：
    1. 广场列表  apiw/v2/copy/leader/list          → 带单员画像
    2. 持仓分布  apiw/v2/copy/leader/position_composition → 当前持仓品种占比
    3. 交易记录  apiw/v2/copy/api/leader/trading_view    → 历史开平仓信号
    4. 带单详情  api/copytrade/copy_trading/trader/detail → 交易标的 + 最大杠杆

    反爬：真实浏览器（无头 new 模式优先，服务器友好）在页面上下文内 fetch，
    携带完整 TLS/JS 指纹与站点 cookie，绕过 Akamai 地域风控；
    有头模式（SCRAPER_HEADLESS=false）需虚拟屏，Docker 内由 xvfb 提供；
    dev 无浏览器时降级 mock 数据（与旧版一致，全链路可测）。
    """

    def __init__(
        self,
        mock: bool | None = None,
        headless: bool | None = None,
        headless_mode: str | None = None,
        page_pool_size: int | None = None,
        data_dir: str | None = None,
    ) -> None:
        settings = get_settings()
        # dev 默认 mock；显式 SCRAPER_REAL=1 或 prod 走真实采集
        self.mock = mock if mock is not None else (settings.app_env == "dev" and not settings.scraper_real)
        # ★ 无头可配置：None=自动(prod 默认无头，服务器友好)，True/False 强制
        self.headless = headless if headless is not None else settings.scraper_headless
        # ★ 无头模式：new(现代无头，指纹难区分，推荐) / old(旧无头，易被检测)
        self.headless_mode = headless_mode or settings.scraper_headless_mode
        # ★ 页面池并发：同一浏览器(context)内并行的页面数（并发拉取多个带单员）
        self.page_pool_size = max(1, page_pool_size or settings.scraper_page_pool_size)
        # ★ 页面池自适应：上限封顶防内存爆；缩容缓冲防跟单波动抖动
        self.max_pages = max(self.page_pool_size, settings.scraper_max_pages)
        self.shrink_buf = max(0, settings.scraper_pool_shrink_buf)
        # ★ 独立 profile 目录：默认 data/scraper（poll_live 热循环专用）；批量任务
        #   （scrape_all/refresh/reconcile）传 scraper_bulk_data_dir 隔离，避免
        #   Chromium ProcessSingleton 同 profile 抢锁互杀。
        self._data_dir = data_dir or settings.scraper_data_dir
        self._browser = None
        self._context = None
        self._pages: list[Any] = []      # 页面池（共享同一会话/指纹）
        self._ready_pages: set[int] = set()  # 已建立会话 cookie 的页面下标
        self._playwright = None
        self._rr = 0  # 轮询分配下标（round-robin）

    # ── 浏览器生命周期（真实采集）──
    @staticmethod
    def _headless_args(headless: bool, mode: str) -> list[str]:
        """按无头模式生成 chromium 启动参数。有头时无需参数。"""
        if not headless:
            return []
        return [f"--headless={mode}"]  # new / old

    async def _ensure_browser(self) -> None:
        if self._pages:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        # 未显式指定 → 默认无头(new)，服务器无需虚拟屏
        headless = True if self.headless is None else self.headless
        mode = self.headless_mode or "new"
        args = self._headless_args(headless, mode)
        settings = get_settings()
        # ★ 方案B：公开爬虫用独立 user_data_dir（scraper_data_dir），与登录会话
        #   (signal_session_data_dir) 彻底隔离，互不争抢 Chrome profile 锁。
        #   公开接口(模式A)走此浏览器；私有接口(模式B)走 signal_session 登录会话。
        #   ★ 批量任务经 data_dir 参数指定 scraper_bulk_data_dir，与 poll 热循环隔离。
        persistent = bool(self._data_dir)
        data_dir = self._data_dir
        proxy = {"server": settings.browser_proxy_url} if settings.browser_proxy_url else None
        try:
            if persistent and self._context is None:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=data_dir,
                    channel="chrome",
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                    proxy=proxy,
                )
                self._browser = self._context.browser
                logger.info("gate scraper: launch persistent chrome (data_dir=%s proxy=%s)", data_dir, settings.browser_proxy_url or "off")
            else:
                browser = await self._playwright.chromium.launch(
                    channel="chrome", headless=headless, args=args, proxy=proxy
                )
                logger.info("gate scraper: launch chrome (headless=%s mode=%s proxy=%s)", headless, mode, settings.browser_proxy_url or "off")
                self._browser = browser
                self._context = await browser.new_context(
                    locale="zh-CN",
                    viewport={"width": 1440, "height": 900},
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                )
        except Exception as exc:  # noqa: BLE001 无系统 Chrome → 内置 chromium
            logger.warning("gate scraper: chrome channel fail (%s), fallback chromium", exc)
            if persistent:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=data_dir,
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                    proxy=proxy,
                )
                self._browser = self._context.browser
            else:
                browser = await self._playwright.chromium.launch(headless=headless, args=args, proxy=proxy)
                self._browser = browser
                self._context = await browser.new_context(
                    locale="zh-CN",
                    viewport={"width": 1440, "height": 900},
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                )
        # ★ 页面池：同一 context 下并行开 N 页，共享同一指纹/cookie，并发 fetch 互不阻塞
        self._pages = [await self._context.new_page() for _ in range(self.page_pool_size)]
        self._ready_pages.clear()

    async def _resize_pool(self, needed: int) -> None:
        """★ 页面池自适应扩缩：按实际监控交易员数动态调整并发页面数。

        - 扩容立即：needed > 当前池 → new_page 追加（共享同一会话/指纹，_api 首次
          请求经 _ensure_page_ready 自动建会话）
        - 缩容保守：当前池 > needed + shrink_buf 才回收尾部页面（防跟单波动抖动，
          避免频繁建/关页面触发 Akamai 重握手）
        - 下限 = 初始池（page_pool_size），上限 = max_pages（防内存爆）
        - 只关尾部页面：保留页面下标不变，_ready_pages 会话 cookie 不失效
        """
        if not self._pages:
            await self._ensure_browser()
        target = min(max(needed, self.page_pool_size), self.max_pages)
        # 扩容：立即追加
        while len(self._pages) < target:
            self._pages.append(await self._context.new_page())
        # 缩容：当前池 > 需要 + 缓冲 才回收尾部多余页面
        if len(self._pages) > target + self.shrink_buf:
            excess = self._pages[target:]
            for p in excess:
                try:
                    await p.close()
                except Exception:  # noqa: BLE001 单页关闭失败不阻断
                    pass
            self._pages = self._pages[:target]
            self._ready_pages = {i for i in self._ready_pages if i < target}

    async def ensure_browser_ready(self, max_wait_s: float = 90.0) -> bool:
        """带重试的浏览器就绪：poll_live / scrape_all / refresh 共用同一
        user_data_dir，Chromium ProcessSingleton 同一时刻只允许一个实例。

        抢锁失败（他任务正持有浏览器）按 2s 退避重试，直到成功或超时返回 False。
        """
        import asyncio
        import time as _time

        deadline = _time.time() + max_wait_s
        while True:
            try:
                await self._ensure_browser()
                return True
            except Exception:  # noqa: BLE001 启动失败 → 清理后重试
                if _time.time() >= deadline:
                    return False
                await self._cleanup_failed_launch()
                await asyncio.sleep(2)

    async def _cleanup_failed_launch(self) -> None:
        """清理启动失败的 playwright 实例，防止重试时驱动进程泄漏。"""
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:  # noqa: BLE001
            pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages = []
        self._ready_pages.clear()

    async def _close_browser(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        self._browser = None
        self._context = None
        self._pages = []
        self._ready_pages.clear()
        self._playwright = None

    async def close(self) -> None:
        """公开关闭浏览器会话（高频轮询任务结束时调用，避免泄漏）。"""
        await self._close_browser()

    async def _ensure_page_ready(self, page: Any, idx: int) -> None:
        """单页首次访问广场页建立会话 cookie；后续复用（高频轮询关键）。

        ★ 冷 profile 首访常被 Akamai 挑战页拦截（容器重建后 profile 归零），
          goto 失败静默 pass 会让本轮全部 fetch 连环失败——加 3 次退避重试，
          通过挑战后 cookie 落盘，后续轮次直接复用。
        """
        if idx in self._ready_pages:
            return
        for attempt in range(3):
            try:
                await page.goto(f"{GATE_BASE}/zh/copytrading", wait_until="domcontentloaded", timeout=60_000)
                self._ready_pages.add(idx)
                return
            except Exception:  # noqa: BLE001
                await asyncio.sleep(2 * (attempt + 1))

    async def _api(self, path: str, params: dict[str, Any], page: Any | None = None) -> dict | None:
        """在浏览器上下文内 fetch（携带页面指纹/cookie），返回 JSON。

        支持并发：传入指定 page（页面池中的某一页）即在该页独立 fetch，
        多页同时 fetch 互不阻塞；不传时 round-robin 分配页面。会话只首次建立。
        """
        await self._ensure_browser()
        if not self._pages:
            return None
        if page is None:
            idx = self._rr % len(self._pages)
            self._rr += 1
            page = self._pages[idx]
        else:
            try:
                idx = self._pages.index(page)
            except ValueError:
                idx = 0
        await self._ensure_page_ready(page, idx)
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        js = (
            f"fetch('{GATE_BASE}{path}?{qs}', {{headers: {{'Accept':'application/json'}}}})"
            ".then(r => r.text())"
        )
        try:
            text = await page.evaluate(js)
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gate api fail %s: %s", path, exc)
            return None

    # ── 公开接口 ──
    @staticmethod
    def _is_test_symbol(symbol: str) -> bool:
        """★ 测试符号过滤：symbol 含 signal_test_symbols 任一标记即视为测试数据。"""
        settings = get_settings()
        up = symbol.upper()
        return any(mark in up for mark in settings.signal_test_symbols)

    @staticmethod
    def _session_fetcher():
        """返回已登录会话的 fetch_api（模式2 私有接口必需）；未启用/异常返回 None。

        ★ 方案B：私有接口(模式2)一律走 signal_session 登录会话，公开爬虫浏览器
           (scraper_data_dir) 不持有登录态，二者彻底隔离。
        """
        settings = get_settings()
        if not settings.signal_session_enabled:
            return None
        try:
            from api.services.signal_session.service import get_signal_session

            return get_signal_session().fetch_api
        except Exception:  # noqa: BLE001
            return None

    async def fetch_top_traders(self, limit: int = 100) -> list[RawTrader]:
        """获取公开带单排行榜（真实：leader/list 分页；dev：mock）。"""
        if self.mock:
            return self._mock_traders(limit)
        traders: list[RawTrader] = []
        page = 1
        while len(traders) < limit:
            resp = await self._api(
                LEADER_LIST_PATH,
                {"page": page, "page_size": min(limit - len(traders), 50), "status": "running", "order_by": "follow_profit", "sort_by": "desc", "cycle": "month", "sub_website_id": 0},
            )
            if not resp or resp.get("code") != 0:
                logger.warning("gate leader/list resp abnormal: %s", str(resp)[:150])
                break
            items = resp["data"]["list"]
            if not items:
                break
            for it in items:
                traders.append(self._to_raw_trader(it))
            if len(items) < 50:
                break
            page += 1
            await asyncio.sleep(random.uniform(1.0, 2.5))
        # ★ 补 7 日收益（week 周期）
        try:
            resp7 = await self._api(
                LEADER_LIST_PATH,
                {"page": 1, "page_size": min(max(len(traders), 20), 50), "status": "running", "order_by": "follow_profit", "sort_by": "desc", "cycle": "week", "sub_website_id": 0},
            )
            if resp7 and resp7.get("code") == 0:
                week_map = {str(it["leader_id"]): self._rate_or_zero(it.get("profit_rate"))
                            for it in resp7["data"]["list"]}
                for t in traders:
                    t.roi_7d = week_map.get(t.trader_id, t.roi_7d)
        except Exception:  # noqa: BLE001
            logger.warning("gate week roi fetch fail")
        # ★ 补全周期画像（detail 接口：累计收益/累计胜率/真实跟单人数/带单天数）
        if not self.mock:
            for t in traders:
                try:
                    detail = await self.get_leader_by_id(t.trader_id)
                    if detail:
                        t.roi_7d = detail.get("roi_7d") or t.roi_7d
                        t.roi_90d = detail.get("roi_90d") or 0
                        t.roi_all = detail.get("roi_all") or 0
                        t.win_rate_30d = detail.get("win_rate_30d") or t.win_rate_30d
                        t.win_rate_all = detail.get("win_rate_all") or 0
                        t.max_drawdown = detail.get("max_drawdown") or t.max_drawdown
                        t.followers = detail.get("followers") or t.followers
                        t.trading_days = detail.get("trading_days") or t.trading_days
                        t.hide_position = detail.get("hide_position")
                except Exception:  # noqa: BLE001 单个失败不阻断
                    logger.warning("gate detail fetch fail: %s", t.trader_id)
                await asyncio.sleep(random.uniform(SCRAPE_MIN_INTERVAL_S, SCRAPE_MAX_INTERVAL_S))
        return traders[:limit]

    async def fetch_trader_positions(self, trader_id: str) -> list[RawPosition]:
        """获取单个带单员实时持仓（★反爬：调用前已按 3-8s 间隔）。"""
        if self.mock:
            return self._mock_positions(trader_id)
        positions: list[RawPosition] = []
        try:
            lid = int(trader_id)
        except ValueError:
            return positions
        # 持仓分布（当前活跃品种占比）→ 主信号
        resp = await self._api(
            LEADER_POSITION_PATH,
            {"leader_id": lid, "data_type": "day", "sub_website_id": 0},
        )
        seen: set[str] = set()
        if resp and resp.get("code") == 200:
            for row in resp.get("data") or []:
                market = row.get("market", "")
                if not market or market in ("others", "USDT"):
                    continue
                sym = market.replace("_", "")
                if self._is_test_symbol(sym):  # ★ 过滤测试符号
                    continue
                seen.add(sym)
                positions.append(
                    RawPosition(
                        trader_id=trader_id,
                        symbol=sym,
                        side="long",  # Gate 占比接口不含方向，默认 long（画像级信号）
                        leverage=1,
                        qty=0.0,
                        entry_price=0.0,
                        # ★ 占比接口无开仓时间：这是「持仓状态」非「交易事件」。
                        #   opened_at=None 标记，调用方跳过信号入库（否则每次采集
                        #   以 now() 生成新 dedupe_key，同一持仓每轮重复记 open）。
                        opened_at=None,
                        raw=row,
                    )
                )
        # 交易记录（最近开仓信号：market + 时间）；已持仓品种跳过，避免重复信号
        resp2 = await self._api(
            LEADER_TRADES_PATH,
            {"leader_id": lid, "data_day": 0, "sub_website_id": 0},
        )
        if resp2 and resp2.get("code") == 0:
            for row in (resp2.get("data") or {}).get("trading_view") or []:
                market = row.get("market", "")
                if not market:
                    continue
                sym = market.replace("_", "")
                if sym in seen:
                    continue
                if self._is_test_symbol(sym):  # ★ 过滤测试符号
                    continue
                seen.add(sym)
                try:
                    ts = int(row.get("data_time", 0))
                    opened = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
                except Exception:  # noqa: BLE001
                    opened = datetime.now(timezone.utc)
                positions.append(
                    RawPosition(
                        trader_id=trader_id,
                        symbol=sym,
                        side="long",
                        leverage=1,
                        qty=0.0,
                        entry_price=0.0,
                        opened_at=opened,
                        raw=row,
                    )
                )
        return positions

    async def fetch_live_positions(self, trader_id: str) -> dict[str, float] | None:
        """快速获取当前持仓快照 {symbol: percent}（实时轮询用，单次 API 调用）。

        percent ∈ [0,1]，如 BTC_USDT 0.4112 = 41.12% 仓位占比。
        返回 None 表示接口失败/风控（调用方应跳过本轮，不更新基线防抖动）；
        返回 {} 表示真空仓（调用方按全平仓处理）。
        """
        if self.mock:
            out: dict[str, float] = {}
            for p in self._mock_positions(trader_id):
                out.setdefault(p.symbol, 0.2)
            return out
        try:
            lid = int(trader_id)
        except ValueError:
            return None
        resp = await self._api(
            LEADER_POSITION_PATH,
            {"leader_id": lid, "data_type": "day", "sub_website_id": 0},
        )
        if not resp or resp.get("code") != 200:
            return None
        snap: dict[str, float] = {}
        for row in resp.get("data") or []:
            market = row.get("market", "")
            if not market or market in ("others", "USDT"):
                continue
            sym = market.replace("_", "")
            if self._is_test_symbol(sym):  # ★ 过滤测试符号
                continue
            snap[sym] = float(row.get("percent") or 0)
        return snap

    async def fetch_trading_records(self, trader_id: str) -> list[RawPosition]:
        """拉取交易记录行（trading_view 接口）—— refresh 兜底详情数据用。

        与 fetch_live_positions（持仓状态）互补：这里返回真实开仓事件行，
        opened_at=接口 data_time（秒级稳定）→ normalizer dedupe_key 跨轮去重，
        重复轮次零噪音。无时间戳的行无法稳定去重，直接跳过。
        """
        positions: list[RawPosition] = []
        if self.mock:
            return positions
        try:
            lid = int(trader_id)
        except ValueError:
            return positions
        resp = await self._api(
            LEADER_TRADES_PATH,
            {"leader_id": lid, "data_day": 0, "sub_website_id": 0},
        )
        if not resp or resp.get("code") != 0:
            return positions
        for row in (resp.get("data") or {}).get("trading_view") or []:
            market = row.get("market", "")
            if not market:
                continue
            sym = market.replace("_", "")
            if self._is_test_symbol(sym):
                continue
            try:
                ts = int(row.get("data_time", 0))
                opened = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            except Exception:  # noqa: BLE001 时间戳异常按无时间戳处理
                opened = None
            if opened is None:
                continue
            positions.append(
                RawPosition(
                    trader_id=trader_id,
                    symbol=sym,
                    side="long",
                    leverage=1,
                    qty=0.0,
                    entry_price=0.0,
                    opened_at=opened,
                    raw=row,
                )
            )
        return positions

    async def fetch_closed_positions(self, trader_id: str, page_size: int = 20) -> list[dict] | None:
        """带单员已平仓记录（close_position 接口）—— 详情页交易记录数据源。

        每行：{gate_order_id, symbol, side, profit, profit_rate, entry_price,
               close_price, qty, leverage, margin, open_time, close_time}
        - side 为真实方向（long/short）；profit/profit_rate 为已实现盈亏/收益率
        - ★ 对隐藏持仓交易员同样完整返回（历史平仓不受 is_hide 屏蔽）
        - 返回 None：接口失败/风控（调用方跳过本轮）；[]：无平仓记录
        """
        if self.mock:
            return []
        try:
            lid = int(trader_id)
        except ValueError:
            return None
        resp = await self._api(
            LEADER_CLOSED_POSITION_PATH,
            {"leader_id": lid, "market": "", "page": 1, "page_size": page_size, "sub_website_id": 0},
        )
        if not resp or resp.get("code") != 200:
            return None
        out: list[dict] = []
        for row in resp.get("data") or []:
            market = row.get("market", "")
            if not market:
                continue
            sym = market.replace("_", "")
            if self._is_test_symbol(sym):
                continue
            try:
                open_ts = int(row.get("open_time") or 0)
                close_ts = int(row.get("create_time") or 0)
            except (TypeError, ValueError):
                continue
            def _f(v) -> float | None:
                try:
                    return float(v) if v not in (None, "") else None
                except (TypeError, ValueError):
                    return None
            out.append({
                "gate_order_id": int(row.get("id") or 0),
                "symbol": sym,
                "side": row.get("side") or "long",
                "profit": _f(row.get("profit")),
                "profit_rate": _f(row.get("profit_rate")),
                "entry_price": _f(row.get("entry_price")),
                "close_price": _f(row.get("close_price")),
                "qty": _f(row.get("qty")),
                "leverage": _f(row.get("leverage_max")),
                "margin": _f(row.get("margin")),
                "open_time": datetime.fromtimestamp(open_ts, tz=timezone.utc) if open_ts else None,
                "close_time": datetime.fromtimestamp(close_ts, tz=timezone.utc) if close_ts else None,
            })
        return out

    async def fetch_leader_positions_live(self, trader_id: str) -> list[dict]:
        """带单员实时持仓行（trader/position 接口）—— 详情页持仓卡片数据源。

        ★ 2026-08-20 详情页抓包确认（与网页"当前持仓"同源）：
          - side: long/short（方向真实，position_composition 无方向）
          - qty: 实际数量（= size × quanto_multiplier，负=空）
          - entry_price/mark_price/unrealised_pnl/margin/position_price(名义价值)
        返回精简 dict 列表；带单员隐藏持仓（is_hide）或空仓 → []。
        """
        out: list[dict] = []
        if self.mock:
            return out
        try:
            lid = int(trader_id)
        except ValueError:
            return out
        resp = await self._api(
            LEADER_LIVE_POSITION_PATH,
            {"leader_id": lid, "sub_website_id": 0},
        )
        if not resp or resp.get("code") != 200:
            return out
        for row in resp.get("data") or []:
            market = row.get("market", "")
            if not market:
                continue
            sym = market.replace("_", "")
            if self._is_test_symbol(sym):
                continue
            try:
                qty = float(row.get("qty") or 0)
            except (TypeError, ValueError):
                qty = 0.0

            def _f(key: str) -> float | None:
                v = row.get(key)
                if v in (None, "", "0"):
                    return None if v in (None, "") else 0.0
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None

            ts = int(row.get("update_time") or 0)
            out.append({
                "symbol": sym,
                "side": str(row.get("side") or ("long" if qty >= 0 else "short")),
                "qty": abs(qty),
                "entry_price": _f("entry_price"),
                "mark_price": _f("mark_price"),
                "unrealized_pnl": _f("unrealised_pnl"),
                "notional_usdt": abs(_f("position_price") or 0.0) or None,
                "margin_usdt": _f("margin"),
                "leverage": None,
                "opened_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                "update_time": ts,
            })
        return out

    async def fetch_profit_chart(self, trader_id: str) -> list[dict]:
        """带单员每日累计收益序列（profit_chart 接口，网页收益走势图同源）。

        data_type=month → 近 30 天每日一行，profit_rate 为累计收益率小数
        （simple_profit_rate 口径，与 roi_all 卡片统一）。返回升序
        [{date, roi_all, create_time}]；接口失败 → []。
        """
        out: list[dict] = []
        if self.mock:
            return out
        try:
            lid = int(trader_id)
        except ValueError:
            return out
        resp = await self._api(
            LEADER_PROFIT_CHART_PATH,
            {"leader_id": lid, "data_type": "month", "sub_website_id": 0},
        )
        if not resp or resp.get("code") != 0:
            return out
        for row in (resp.get("data") or {}).get("list") or []:
            ts = int(row.get("create_time") or 0)
            if not ts:
                continue
            try:
                rate = float(row.get("profit_rate") or 0)
            except (TypeError, ValueError):
                continue
            d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            out.append({"date": d, "roi_all": round(rate * 100, 2), "create_time": ts})
        out.sort(key=lambda r: r["create_time"])
        return out

    async def fetch_live_positions_many(
        self, trader_ids: list[str]
    ) -> dict[str, dict[str, float] | None]:
        """★ 页面池并发：一次批量拉取多个带单员持仓快照。

        同一浏览器(context)的页面池内并发 fetch，每个请求落在不同 page 上互不阻塞，
        结束单轮耗时从「交易员数 × 单次往返」降到「(交易员数/池大小) × 单次往返」。
        返回 {trader_id: {sym: percent} | None}，None 表示该交易员接口失败。
        """
        if not trader_ids:
            return {}
        # ★ 页面池自适应：按实际监控交易员数扩缩并发页面（扩容立即/缩容保守/上限封顶）
        await self._resize_pool(len(trader_ids))
        if not self._pages:
            return {tid: None for tid in trader_ids}
        # 并发上限 = 当前页面池大小；为防过度并发，用信号量限制并发数
        sem = asyncio.Semaphore(len(self._pages))

        async def _one(tid: str) -> tuple[str, dict[str, float] | None]:
            async with sem:
                # 分配本请求专用 page（round-robin），并发 fetch 互不阻塞
                idx = self._rr % len(self._pages)
                self._rr += 1
                page = self._pages[idx]
                resp = await self._api(
                    LEADER_POSITION_PATH,
                    {"leader_id": tid, "data_type": "day", "sub_website_id": 0},
                    page=page,
                )
                if not resp or resp.get("code") != 200:
                    return tid, None
                snap: dict[str, float] = {}
                for row in resp.get("data") or []:
                    market = row.get("market", "")
                    if not market or market in ("others", "USDT"):
                        continue
                    sym = market.replace("_", "")
                    if self._is_test_symbol(sym):  # ★ 过滤测试符号
                        continue
                    snap[sym] = float(row.get("percent") or 0)
                return tid, snap

        results = await asyncio.gather(*(_one(tid) for tid in trader_ids))
        return dict(results)

    # ── 模式2 信号源：跟单账户持仓（★监控自己跟单交易员的镜像仓位）──
    #   ★ 关键：follower/position 返回的是「本账号已跟单」的镜像仓位，每行自带 trader_info.leader_id。
    #   ★ 必须按 leader_id 精确归属，绝不能用 trader_name 覆盖——否则会把跟单账户里其他带单员的
    #     仓位误标为主体带单员（带单员隐藏仓位时尤为致命）。差分引擎据此按 leader_id 隔离。
    async def fetch_followed_leaders(
        self, status: str = "running", fetcher=None
    ) -> list[tuple[str, str]] | None:
        """自动发现「已跟单」的交易员列表（★ 2026-08 实测 /api/copytrade/copy_trading/follow/order）。

        - 返回 [(leader_id, nick), ...]：全部已跟单交易员，**含当前空仓的**（position 接口不返回空仓行）。
        - 返回 None：接口失败/未登录（调用方跳过本轮）。
        - fetcher：可选。传 signal_session.fetch_api 时复用持久化登录会话（★ 推荐，避免
          与登录会话争抢同一 user_data_dir 导致 profile 锁冲突）；None 走自身 _api。
        - ★ 用途：空仓交易员在 follower/position 不可见，必须靠此接口自动发现其 leader_id，
          避免手动维护 signal_follower_leader_ids 配置漏掉新跟单交易员。
        """
        if self.mock:
            return [("32801", "复利如慢牛"), ("24264", "风懃")]
        # ★ 方案B：私有接口默认走登录会话（未显式传 fetcher 时）
        fetcher = fetcher or self._session_fetcher()
        resp = await fetcher(
            FOLLOW_ORDER_PATH,
            {"page": 1, "page_size": 50, "status": status, "asset": "", "market": ""},
        ) if fetcher is not None else await self._api(
            FOLLOW_ORDER_PATH,
            {"page": 1, "page_size": 50, "status": status, "asset": "", "market": ""},
        )
        if not resp or resp.get("code") != 200:
            logger.warning("gate follow/order 接口异常: %s", str(resp)[:150])
            return None
        data = resp.get("data") or {}
        orders = data.get("orders") or []
        out: list[tuple[str, str]] = []
        for o in orders:
            lid = o.get("leader_id")
            if lid is None:
                continue
            info = o.get("trader_info") or {}
            nick = info.get("nick") or info.get("nickname") or f"Leader{lid}"
            out.append((str(lid), nick))
        return out

    async def search_leaders(self, keyword: str, page: int = 1, page_size: int = 20,
                             fetcher=None) -> list[dict] | None:
        """按昵称/ID 搜索带单员（★ 需求：后台「搜索跟单交易员」只展示，不跟单）。

        走 /apiw/v2/copy/leader/search?name=<kw>（★ 2026-08 实测参数名是 name，非 keyword）。
        - fetcher：可选。传 signal_session.fetch_api 时复用持久化登录会话（★ 推荐，避免
          新建浏览器与登录会话争抢同一 user_data_dir 导致 profile 锁冲突）；None 走自身 _api。
        - 返回 [{leader_id, nick, roi_30d, win_rate, ...}]：模糊匹配列表（含匿名昵称）。
        - 返回 None：接口失败/未登录（需已登录的持久化浏览会话）。
        """
        if not keyword or not keyword.strip():
            return []
        if self.mock:
            return [{"leader_id": "24264", "nick": "风懃", "roi_30d": 3.2, "win_rate_all": 61.0}]
        # ★ 方案B：私有接口默认走登录会话（未显式传 fetcher 时）
        fetcher = fetcher or self._session_fetcher()
        resp = await fetcher(
            LEADER_SEARCH_PATH,
            {"name": keyword.strip(), "page": page, "page_size": page_size},
        ) if fetcher is not None else await self._api(
            LEADER_SEARCH_PATH,
            {"name": keyword.strip(), "page": page, "page_size": page_size},
        )
        if not resp or resp.get("code") != 0:
            logger.warning("gate leader/search 接口异常: %s", str(resp)[:150])
            return None
        items = (resp.get("data") or {}).get("list") or []
        out: list[dict] = []
        for it in items:
            user = it.get("user_info") or {}
            out.append({
                "leader_id": it.get("leader_id"),
                "nick": user.get("nick") or user.get("nickname") or "",
                "roi_30d": self._rate_or_zero(it.get("profit_rate")),
                "win_rate_all": self._to_pct(it.get("win_rate")),
                "max_drawdown": self._to_pct(it.get("max_drawdown")),
                "followers": it.get("curr_follow_num") or 0,
                "is_follow": it.get("is_follow") or False,
                "is_full": it.get("is_full") or False,
            })
        return out

    @staticmethod
    def _to_pct(v) -> float:
        """把接口小数比例(0.2346)转百分比(23.46)。空/非法返回 0。"""
        try:
            return round(float(v) * 100, 2)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _rate_or_zero(cls, v, fallback=None) -> float:
        """★ Gate 收益率字段哨兵值处理：-1 表示「收益已重置/无数据」（实测 12221：
        profit_rate=-1 但 profit=+5121U、胜率/带单天数均正常）。盲目 ×100 会把健康
        交易员显示成 -100% 全亏。哨兵 → 回退备用字段，备用也无效则 0（未知）。
        """
        pct = cls._to_pct(v)
        if pct > -99.99:
            return pct
        if fallback is not None:
            fb = cls._to_pct(fallback)
            if fb > -99.99:
                return fb
        return 0.0

    async def get_leader_by_id(self, leader_id: str, fetcher=None) -> dict | None:
        """★ 按 ID 精确查带单员画像（★ 兜底：search 只按昵称匹配，纯数字 ID 返回空）。

        走 /api/copytrade/copy_trading/trader/detail/{id}（★ 2026-08 实测返回完整画像）。
        - fetcher：可选。传 signal_session.fetch_api 时复用持久化登录会话（★ 推荐，避免
          与登录会话争抢同一 user_data_dir 导致 profile 锁冲突）；None 走自身 _api。
        - 返回 dict：{leader_id, nick, roi_7d, roi_30d, roi_90d, roi_all,
          win_rate_30d, win_rate_all, max_drawdown, followers, trading_days,
          is_follow, is_full, style, abstract, markets, min_follow_amount, max_follow_amount}
        - 返回 None：接口失败/未登录。
        - 注意：detail 接口不返回昵称字段，nick 用 "Leader{id}" 占位，前端可自行补全。
        """
        if not str(leader_id).strip().isdigit():
            return None
        if self.mock:
            return {"leader_id": "24264", "nick": "Leader24264",
                    "roi_7d": 1.2, "roi_30d": -64.42, "roi_90d": -30.5, "roi_all": -80.0,
                    "win_rate_30d": 38.0, "win_rate_all": 40.1,
                    "max_drawdown": 34.77, "followers": 1, "trading_days": 120,
                    "is_follow": False, "is_full": False, "style": "high-frequence|short-line",
                    "abstract": "市场永远是对的，做市场的朋友，顺势而为！",
                    "min_follow_amount": "10", "max_follow_amount": "50000",
                    "hide_position": False}
        path = LEADER_DETAIL_PATH.format(leader_id=str(leader_id).strip())
        resp = await fetcher(
            path, {"sub_website_id": 0},
        ) if fetcher is not None else await self._api(path, {"sub_website_id": 0})
        if not resp or resp.get("code") != 200:
            logger.warning("gate trader/detail 接口异常: %s", str(resp)[:150])
            return None
        data = resp.get("data") or {}
        config = data.get("config") or {}
        profit = data.get("profit") or {}
        win_num = profit.get("win_num") or 0
        loss_num = profit.get("loss_num") or 0
        total = win_num + loss_num
        return {
            "leader_id": str(config.get("leader_id") or leader_id),
            "nick": f"Leader{leader_id}",
            # ★ 详情接口多周期字段：7d/30d/90d 均为小数比例(×100 转百分数)；
            #   -1 哨兵（收益重置/无数据）→ 0
            "roi_7d": self._rate_or_zero(profit.get("seven_profit_rate")),
            "roi_30d": self._rate_or_zero(profit.get("month_profit_rate")),
            "roi_90d": self._rate_or_zero(profit.get("three_month_profit_rate")),
            # ★ roi_all 用 simple_profit_rate 口径（2026-08-20 与 profit_chart 曲线终点
            #   实测对齐）：profit.profit_rate 是含跟随者分成口径（27714 实测 728% vs
            #   网页收益曲线/simple 口径 169%），卡片与曲线不同口径会造成割裂。
            "roi_all": self._rate_or_zero(profit.get("simple_profit_rate"),
                                          fallback=profit.get("profit_rate")),
            "win_rate_30d": self._to_pct(profit.get("month_win_rate")),
            "win_rate_all": round(win_num / total * 100, 1) if total else 0.0,
            "max_drawdown": self._to_pct(profit.get("max_drawdown")),  # 全周期回撤
            "followers": profit.get("curr_follow_num") or 0,  # 真实当前跟单人数
            "trading_days": int(profit.get("duration_day") or 0),  # 带单天数
            "is_follow": bool(config.get("is_self")) or False,
            "is_full": bool(profit.get("is_full")) or False,
            # ★ 是否隐藏当前持仓（config.is_hide）：True=带单员关闭持仓公开，
            #   公开采集(trader/position/占比接口)拿不到其仓位 → 上架只能走模式B
            "hide_position": bool(config.get("is_hide")) if config.get("is_hide") is not None else None,
            "style": config.get("style") or "",
            "abstract": config.get("abstract") or "",
            "markets": [m.get("market") for m in (config.get("markets") or [])][:15],
            "min_follow_amount": config.get("min_follow_amount") or "",
            "max_follow_amount": config.get("max_follow_amount") or "",
        }

    async def fetch_follower_positions(self) -> list[RawPosition] | None:
        """拉取当前账号跟单账户的全部持仓（模式2 信号源）。

        - 返回 None：接口失败/未登录（调用方本轮跳过，不更新基线防抖动）
        - 返回 []：登录成功但当前无任何跟单持仓（真空仓 → 按全平仓处理）
        - 返回 list：每个 RawPosition.trader_id = 归属带单员 leader_id，trader_name = nick
        """
        if self.mock:
            return self._mock_follower_positions()
        # ★ 方案B：私有接口默认走登录会话（未显式传 fetcher 时）
        fetcher = self._session_fetcher()
        resp = await fetcher(
            FOLLOWER_POSITION_PATH,
            {"trader_name": "", "market": "", "page": 1, "page_size": 100, "sub_website_id": 0},
        ) if fetcher is not None else await self._api(
            FOLLOWER_POSITION_PATH,
            {"trader_name": "", "market": "", "page": 1, "page_size": 100, "sub_website_id": 0},
        )
        if not resp or resp.get("code") != 200:
            logger.warning("gate follower/position 接口异常: %s", str(resp)[:150])
            return None
        return self._parse_follower_positions(resp)

    async def fetch_follower_positions_many(
        self, leader_ids: list[str]
    ) -> dict[str, list[RawPosition] | None]:
        """拉取全部跟单持仓一次，按 leader_id 分组（★避免按名多次调用导致归属混淆）。

        返回 {leader_id: [RawPosition, ...] | None}；None=整体接口失败，
        [] 表示该 leader 无镜像持仓（未跟单 / 已清仓）。
        """
        if not leader_ids:
            return {}
        all_pos = await self.fetch_follower_positions()
        if all_pos is None:
            return {lid: None for lid in leader_ids}
        grouped: dict[str, list[RawPosition]] = {}
        for p in all_pos:
            grouped.setdefault(p.trader_id, []).append(p)
        return {lid: grouped.get(str(lid), []) for lid in leader_ids}

    async def fetch_follower_snapshots(
        self, leader_ids: list[str]
    ) -> dict[str, dict[str, float] | None]:
        """拉取全部跟单持仓一次，按 leader_id 分组成 {symbol: qty} 快照（模式2 差分用）。

        - {leader_id: {sym: qty}}：该带单员在跟单账户的镜像持仓（qty=跟单数量）
        - {leader_id: None}：整体接口失败（调用方跳过本轮）
        - {leader_id: {}}：该带单员无镜像持仓（未跟单 / 已清仓）
        """
        if not leader_ids:
            return {}
        all_pos = await self.fetch_follower_positions()
        if all_pos is None:
            return {lid: None for lid in leader_ids}
        snap: dict[str, dict[str, float]] = {}
        for p in all_pos:
            snap.setdefault(p.trader_id, {})[p.symbol] = p.qty
        out: dict[str, dict[str, float] | None] = {}
        for lid in leader_ids:
            out[lid] = snap.get(str(lid), {})
        return out

    @staticmethod
    def _parse_follower_positions(resp: dict) -> list[RawPosition]:
        """解析 /apiw/v2/copy/follower/position 返回 → RawPosition 列表。

        ★★ 字段口径（★ 2026-08 真实报文校准）：
          - leader_id 在数据行【顶层】row["leader_id"]（int，如 32801），
            绝不在 trader_info 里；trader_info 只有 nick/nickname/anonymous。
          - qty 取 row["qty"]（跟单数量，如 "0.001"），不是 size("0.1")——size 是张数。
          - leverage 回退：跟单接口 leverage 恒为 "0"，真实最大杠杆在 cross_leverage_limit。
          - market "ETH_USDT" → 标准化 "ETHUSDT"。
          - side 已含真实方向 short/long。
        ∴ trader_id 必须取顶层 leader_id，否则归属为空 → 无法按带单员隔离（致命）。
        """
        settings = get_settings()
        out: list[RawPosition] = []
        now = datetime.now(timezone.utc)
        for row in resp.get("data") or []:
            market = row.get("market", "")
            if not market or market.lower() in ("others", "usdt"):
                continue
            sym = market.replace("_", "")
            up_sym = sym.upper()
            if any(mark in up_sym for mark in settings.signal_test_symbols):  # ★ 测试符号过滤
                continue
            # 方向：接口返回 short/sell/long；未知默认 long
            side = "short" if str(row.get("side", "")).lower() in ("short", "sell", "1") else "long"
            try:
                qty = float(row.get("qty") or 0)
            except (TypeError, ValueError):
                qty = 0.0
            try:
                entry = float(row.get("entry_price") or 0)
            except (TypeError, ValueError):
                entry = 0.0
            # ★ 跟单接口 leverage 恒 "0"，回退 cross_leverage_limit（真实最大杠杆）
            try:
                lev = int(float(row.get("leverage") or 0))
            except (TypeError, ValueError):
                lev = 0
            if lev <= 0:
                try:
                    lev = int(float(row.get("cross_leverage_limit") or 0))
                except (TypeError, ValueError):
                    lev = 0
            # ★ 归属：顶层 leader_id（真实唯一标识），trader_info 仅作展示 nick
            trader_id = row.get("leader_id")
            if trader_id is None:
                trader_id = (row.get("trader_info") or {}).get("leader_id")  # 兜底兼容
            out.append(
                RawPosition(
                    trader_id=str(trader_id or ""),
                    symbol=sym,
                    side=side,
                    leverage=lev,
                    qty=qty,
                    entry_price=entry,
                    opened_at=now,
                    raw=row,
                )
            )
        return out

    async def scrape_all_traders(self, limit: int = 100) -> AsyncIterator[tuple[RawTrader, list[RawPosition]]]:
        """全量采集：排行榜 → 逐个带单员持仓页（★反爬间隔 3-8s）。"""
        traders = await self.fetch_top_traders(limit)
        for t in traders:
            await asyncio.sleep(random.uniform(SCRAPE_MIN_INTERVAL_S, SCRAPE_MAX_INTERVAL_S))
            positions = await self.fetch_trader_positions(t.trader_id)
            yield t, positions
        await self._close_browser()

    # ── 真实数据解析 ──
    @staticmethod
    def _to_raw_trader(it: dict) -> RawTrader:
        user = it.get("user_info") or {}
        # ★ 排行榜接口 cycle=month 只返回「月周期」数据：只填 30d 字段，
        #   7d/90d/all 由 fetch_top_traders 补拉 week 周期与 detail 接口填充，避免字段复制失真
        #   ★ profit_rate -1 哨兵（收益重置/无数据）→ 0，防显示 -100%
        month_roi = GateScraper._rate_or_zero(it.get("profit_rate"))
        return RawTrader(
            trader_id=str(it["leader_id"]),
            name=user.get("nick") or user.get("nickname") or f"Leader{it['leader_id']}",
            followers=int(it.get("curr_follow_num") or 0),
            roi_30d=month_roi,          # 月收益（cycle=month）
            win_rate_30d=float(it.get("win_rate") or 0) * 100,  # 月胜率
            max_drawdown=float(it.get("max_drawdown") or 0) * 100,  # 月回撤
            trading_days=int(it.get("leading_days") or 0),
            raw=it,
        )

    # ── mock 数据（dev 无浏览器降级）──
    def _mock_traders(self, limit: int) -> list[RawTrader]:
        seeds = [
            ("T-ALPHA", "AlphaBreakout", 12840, 18.5, 42.1, 68.3, 210.4, 68.2, 66.8, 18.2, 96),
            ("T-BETA", "BetaMomentum", 9531, 12.2, 33.8, 55.9, 142.7, 64.5, 63.1, 22.4, 120),
            ("T-GAMMA", "GammaSwing", 7620, 8.9, 27.4, 48.6, 98.3, 61.8, 60.2, 25.8, 88),
            ("T-DELTA", "DeltaScalper", 18430, 22.7, 51.2, 79.5, 268.9, 72.4, 70.9, 15.6, 154),
            ("T-EPSILON", "EpsilonGrid", 4312, 5.4, 19.6, 33.2, 61.5, 56.3, 55.8, 28.1, 66),
            ("T-ZETA", "ZetaArb", 2988, -3.2, 11.8, 24.7, 48.9, 54.1, 52.7, 31.4, 42),
            ("T-ETA", "EtaTrend", 11220, 15.1, 38.9, 61.4, 175.2, 66.2, 64.9, 19.7, 108),
            ("T-THETA", "ThetaRange", 5876, 7.3, 24.5, 41.8, 87.6, 59.7, 58.4, 24.6, 75),
        ]
        out = []
        for i, (tid, name, fol, r7, r30, r90, ra, w30, wa, dd, days) in enumerate(seeds):
            if i >= limit:
                break
            out.append(
                RawTrader(
                    trader_id=tid, name=name, followers=fol,
                    roi_7d=r7, roi_30d=r30, roi_90d=r90, roi_all=ra,
                    win_rate_30d=w30, win_rate_all=wa, max_drawdown=dd, trading_days=days,
                    raw={"source": "mock"},
                )
            )
        return out

    def _mock_positions(self, trader_id: str) -> list[RawPosition]:
        pos_map: dict[str, list[tuple]] = {
            "T-ALPHA": [("BTCUSDT", "long", 10, 0.8, 96500.0), ("ETHUSDT", "long", 5, 6.2, 3420.0)],
            "T-BETA": [("SOLUSDT", "long", 20, 15.0, 168.5)],
            "T-DELTA": [("BTCUSDT", "short", 15, 0.5, 96400.0), ("BNBUSDT", "long", 8, 3.1, 586.0)],
            "T-ETA": [("ETHUSDT", "long", 10, 4.0, 3405.0)],
        }
        out = []
        now = datetime.now(timezone.utc)
        for i, (sym, side, lev, qty, price) in enumerate(pos_map.get(trader_id, [])):
            opened = now.replace(microsecond=0)
            out.append(
                RawPosition(
                    trader_id=trader_id, symbol=sym, side=side, leverage=lev,
                    qty=qty, entry_price=price, opened_at=opened,
                    raw={"source": "mock"},
                )
            )
        return out

    def _mock_follower_positions(self) -> list[RawPosition]:
        """dev mock：跟单账户持仓（镜像复利如慢牛 ETH 空单，方向真实）。"""
        now = datetime.now(timezone.utc)
        return [
            RawPosition(
                trader_id="32801",
                symbol="ETHUSDT",
                side="short",
                leverage=50,
                qty=0.001,
                entry_price=1886.04,
                opened_at=now,
                raw={"source": "mock", "trader_info": {"nick": "复利如慢牛", "leader_id": 32801}},
            )
        ]
