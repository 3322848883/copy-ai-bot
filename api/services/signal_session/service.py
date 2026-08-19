# -*- coding: utf-8 -*-
"""模式2 信号源·持久化浏览器会话服务（后台管理「登录 Gate」）。

核心：在服务器端维护一个持久化 Chrome(user_data_dir)，把 Gate 登录态自动落盘，
通过「截图推送 + 输入事件转发」在后台管理界面远程操作该浏览器完成登录
（含验证码/滑块，由真人完成人机验证），之后供 `fetch_follower_positions` 复用。

设计要点：
- 持久化：`chromium.launch_persistent_context(user_data_dir=...)`，登录态自动存盘，
  重启/信号源复用同一目录即恢复登录，无需重新登录。
- 远程串流：截图轮询(screenshot) + 输入事件转发(dispatch_event)，跨设备可用。
- 单例：全局仅一个会话实例，避免多 worker 争用同一 user_data_dir。

状态机：idle → launching → active → logged_in；active 可回到 idle（close）。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from api.core.config import get_settings

logger = logging.getLogger("signal-saas.signal_session")

GATE_BASE = "https://www.gate.com"
GATE_LOGIN_URL = f"{GATE_BASE}/login"
GATE_COPY_MINE_URL = f"{GATE_BASE}/zh/copytrading/mine?mode=futures&type=copy"

# 判定已登录：跟单账户接口返回 code=200 即视为会话有效（需带登录 cookie）
_CHECK_PATH = "/apiw/v2/copy/follower/position"


@dataclass
class SessionStatus:
    state: str                                  # idle / launching / active / logged_in
    logged_in: bool = False
    trader_count: int = 0                       # 当前跟单交易员数（登录成功后可读）
    message: str = ""
    url: str = ""
    has_persisted: bool = False                 # user_data_dir 是否已存在登录态
    source_mode: str = "follower"               # 固定：模式2 跟单账户


# 登录态跨进程标记：uvicorn(admin) 与 celery worker 是独立进程、各自持有独立单例，
# 但共享同一 user_data_dir。浏览器由"最后使用它的进程"持有（profile 锁互斥），
# 因此本进程未必持有浏览器。__loginstate.json 用于把"已确认登录"持久化，
# 供无浏览器的进程（如 admin /status）据此展示 logged_in（绿点），避免一直"连接中"。
_LOGIN_MARKER = ".loginstate.json"

# ★ 管理员操作独占标志（Redis）：admin 通过 /start 拉起浏览器远程操作期间，
#   worker 的 fetch_api 不得强制拉起浏览器争抢同一 user_data_dir（ProcessSingleton
#   冲突会让 admin 的会话崩溃）。worker 各采集点调用前须检查此标志。
_ADMIN_HOLD_KEY = "signal_session:admin_hold"


class SignalSession:
    """单例：模式2 持久化浏览器会话。

    线程/进程安全说明：本服务运行在 FastAPI 的 asyncio 事件循环内，
    browser/context 均在当前 loop 创建，方法为 async，不需额外锁。
    生产多 worker 时需将本服务限定在单 worker（见 _ensure_single_worker）。
    """

    def __init__(self) -> None:
        self._playwright: Any = None
        self._context: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._state = "idle"
        self._data_dir: str | None = None

    # ── 登录态跨进程标记 ──
    @staticmethod
    def _marker_path() -> str:
        return os.path.join(get_settings().signal_session_data_dir, _LOGIN_MARKER)

    def _write_marker(self, logged_in: bool, trader_count: int = 0, message: str = "") -> None:
        """把登录态确认结果落盘，供其它进程（uvicorn admin）展示绿点。"""
        try:
            data = {
                "logged_in": bool(logged_in),
                "trader_count": int(trader_count),
                "message": message,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            os.makedirs(os.path.dirname(self._marker_path()), exist_ok=True)
            with open(self._marker_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:  # noqa: BLE001 标记写入失败不阻断主流程
            logger.warning("signal session: 写登录态标记失败")

    @staticmethod
    def _read_marker() -> dict:
        try:
            with open(SignalSession._marker_path()) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}

    def _has_persisted_dir(self) -> bool:
        return os.path.isdir(get_settings().signal_session_data_dir)

    # ── 管理员操作独占标志（Redis，跨进程） ──
    @staticmethod
    def acquire_admin_hold(ttl_s: int = 900) -> bool:
        """admin 拉起远程浏览器时占用（TTL 兜底防忘记释放）。已占用返回 False。"""
        try:
            import redis

            r = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
            ok = r.set(_ADMIN_HOLD_KEY, "1", nx=True, ex=ttl_s)
            r.close()
            return bool(ok)
        except Exception:  # noqa: BLE001 Redis 不可用不阻断 admin 操作
            return True

    @staticmethod
    def release_admin_hold() -> None:
        try:
            import redis

            r = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
            r.delete(_ADMIN_HOLD_KEY)
            r.close()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def refresh_admin_hold(ttl_s: int = 900) -> None:
        """续期独占标志（仅已存在时）：admin 远程视图的截图轮询作为心跳。"""
        try:
            import redis

            r = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
            if r.get(_ADMIN_HOLD_KEY):
                r.expire(_ADMIN_HOLD_KEY, ttl_s)
            r.close()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def admin_hold_active() -> bool:
        """worker 采集点调用 signal_session 前检查：admin 正在远程操作则跳过本轮。"""
        try:
            import redis

            r = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
            v = r.get(_ADMIN_HOLD_KEY)
            r.close()
            return bool(v)
        except Exception:  # noqa: BLE001 Redis 故障放行 worker（保持采集可用）
            return False

    # ── 生命周期 ──
    async def start_login(self, force_launch: bool = False) -> SessionStatus:
        """启动持久化浏览器并打开 Gate 登录页（后台管理远程操作起点）。

        force_launch=True：fetch_api 需要真实可用的浏览器来调 follow/order 接口，
        必须真正拉起，不能仅因标记存在而短路（否则 worker 每次 close 后无法复用，
        导致 mode2 监控永久失效）。仅 admin 显式 /start 时走标记短路避免争抢锁。
        """
        if self._page is not None:
            return self.status()
        # ★ 已有跨进程确认的有效登录时，直接复用标记（仅 admin 显式启动，避免与 worker 争抢 profile 锁）
        marker = self._read_marker()
        if not force_launch and marker.get("logged_in"):
            return SessionStatus(
                "logged_in",
                logged_in=True,
                trader_count=int(marker.get("trader_count") or 0),
                message=marker.get("message") or "已复用持久化登录态（其他进程正在使用该会话）",
                has_persisted=True,
                source_mode="follower",
            )
        settings = get_settings()
        self._data_dir = settings.signal_session_data_dir
        self._state = "launching"
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            headless = True if settings.signal_session_headless is None else settings.signal_session_headless
            proxy = {"server": settings.browser_proxy_url} if settings.browser_proxy_url else None
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self._data_dir,
                    channel="chrome",
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                    proxy=proxy,
                )
                logger.info("gate signal session: launch persistent chrome (headless=%s proxy=%s)", headless, settings.browser_proxy_url or "off")
            except Exception as exc:  # noqa: BLE001 无系统 Chrome → 内置 chromium
                logger.warning("gate signal session: chrome channel fail (%s), fallback chromium", exc)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self._data_dir,
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                    proxy=proxy,
                )
            self._browser = self._context.browser
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            # 若已有登录态(user_data_dir 非空)，直接进已登录; 否则进登录页
            await self._page.goto(GATE_COPY_MINE_URL, wait_until="domcontentloaded", timeout=60_000)
            self._state = "active"
            # ★ 自动识别登录态：持久化 cookie 仍有效时直接置 logged_in，无需人工点「完成登录」
            try:
                ok, count = await self._check_logged_in()
            except Exception:  # noqa: BLE001
                ok, count = False, 0
            if ok:
                self._state = "logged_in"
                self._write_marker(True, count, "自动识别：复用已持久化登录态")
            else:
                # ★ 自愈历史假标记：检测失败必须回写 false，否则假 logged_in 标记
                #   会让 /status 永远显示绿点、误导管理员
                self._write_marker(False, 0, "登录态已失效，请在视图中重新登录")
            return self.status()
        except Exception as exc:  # noqa: BLE001
            logger.exception("signal session start_login failed")
            # ★ 泄漏根治：拉起失败（典型 TargetClosedError=目录被其他容器僵尸 chrome 持锁）
            #   必须清理本进程已 spawn 的 playwright/chrome，否则每次失败泄漏一组进程。
            try:
                await self.close()
            except Exception:  # noqa: BLE001
                pass
            self._kill_stale_chrome(exc)
            self._state = "idle"
            return SessionStatus("idle", message=f"启动失败: {exc}")

    @staticmethod
    def _kill_stale_chrome(exc: Exception) -> None:
        """拉起失败时清理本容器残留 chrome 进程（TargetClosedError 场景）。

        Chrome 主进程可能已 spawn 但 playwright 连接失败即放弃，进程树成为孤儿
        （容器无 init 时永久残留，并持有 user_data_dir 的 SingletonLock——
        之后本容器及其他容器共享该目录的浏览器全部拉不起来，模式2 整链路瘫痪）。
        """
        import subprocess

        try:
            r = subprocess.run(
                ["pkill", "-9", "-f", "chrome"], capture_output=True, timeout=15
            )
            logger.warning(
                "gate signal session: 拉起失败(%s)，已清理残留 chrome 进程 (rc=%s)",
                type(exc).__name__, r.returncode,
            )
        except Exception as cleanup_exc:  # noqa: BLE001 清理失败不影响返回
            logger.warning("gate signal session: 清理残留 chrome 失败: %s", cleanup_exc)

    async def screenshot(self) -> bytes | None:
        """返回当前浏览器页面 PNG 字节（后台管理轮询显示）。会话未激活返回 None。"""
        if self._page is None:
            return None
        try:
            return await self._page.screenshot(type="png")
        except Exception:  # noqa: BLE001
            return None

    async def dispatch_event(self, event: dict[str, Any]) -> None:
        """把后台管理界面捕获的用户输入转发到远程浏览器。

        event = {"type": "click|mousemove|mousedown|mouseup|wheel|keydown|keyup|type|press|navigate", ...}
        坐标基于远程页面 viewport(1440x900)，前端需按显示比例换算。
        """
        if self._page is None:
            return
        page = self._page
        etype = event.get("type", "")
        try:
            if etype == "navigate":
                await page.goto(event.get("url") or GATE_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            elif etype == "mousemove":
                await page.mouse.move(event["x"], event["y"])
            elif etype in ("mousedown", "mouseup"):
                btn = {"left": "left", "right": "right", "middle": "middle"}.get(
                    event.get("button", "left"), "left"
                )
                fn = page.mouse.down if etype == "mousedown" else page.mouse.up
                await fn(button=btn)
            elif etype == "click":
                btn = {"right": "right", "middle": "middle"}.get(event.get("button", "left"), "left")
                await page.mouse.click(event["x"], event["y"], button=btn)
            elif etype == "wheel":
                await page.mouse.wheel(event.get("deltaX", 0), event.get("deltaY", 0))
            elif etype == "type":
                await page.keyboard.type(event.get("text", ""))
            elif etype == "press":
                await page.keyboard.press(event.get("key", "Enter"))
            elif etype == "keydown":
                await page.keyboard.down(event.get("key", ""))
            elif etype == "keyup":
                await page.keyboard.up(event.get("key", ""))
        except Exception:  # noqa: BLE001
            logger.warning("signal session dispatch_event failed: %s", etype)

    async def complete_login(self) -> SessionStatus:
        """用户完成登录后调用：校验会话有效性并持久化（user_data_dir 已自动落盘）。"""
        if self._page is None:
            return self.status()
        ok, count = await self._check_logged_in()
        self._state = "logged_in" if ok else "active"
        # ★ 登录态标记落盘：供 uvicorn 看板据此显示绿点（跨进程）
        self._write_marker(ok, count, "登录成功，会话已持久化" if ok else "尚未检测到有效登录")
        return SessionStatus(
            self._state,
            logged_in=ok,
            trader_count=count,
            message="登录成功，会话已持久化" if ok else "尚未检测到有效登录，请完成账号密码/验证码",
            url=self._page.url if self._page else "",
            has_persisted=True,
        )

    async def _check_logged_in(self) -> tuple[bool, int]:
        """在页面内 fetch 跟单账户接口，判断登录态；返回 (是否登录, 跟单交易员数)。

        ★ 严格校验（三层）：
          1. 页面 URL 含 /login → Gate 已重定向到登录页，必为未登录；
          2. fetch 需 HTTP 200 且业务 code===200；
          3. evaluate 异常/返回非法值一律视为未登录。
          （follower/position 接口对匿名会话也可能返回 code 200 空数据，
            仅靠接口返回判定会写出假登录标记，导致 /start 短路死锁。）
        """
        if self._page is None:
            return False, 0
        # ★ URL 兜底：跳转到登录页 = 未登录
        try:
            url = self._page.url or ""
            if "/login" in url:
                return False, 0
        except Exception:  # noqa: BLE001
            return False, 0
        try:
            js = (
                f"fetch('{GATE_BASE}{_CHECK_PATH}?trader_name=&market=&page=1&page_size=100&sub_website_id=0',"
                "{credentials:'include'}).then(r=>r.status===200?r.json().then(d=>"
                "({ok:d&&d.code===200,n:d&&d.data?d.data.length:0})"
                ").catch(()=>null):null).catch(()=>null)"
            )
            resp = await self._page.evaluate(f"({js})")
            if not isinstance(resp, dict) or resp.get("ok") is not True:
                return False, 0
            try:
                count = int(resp.get("n") or 0)
            except (TypeError, ValueError):
                count = 0
            return True, count
        except Exception:  # noqa: BLE001
            return False, 0

    async def fetch_api(self, path: str, params: dict[str, Any] | None = None) -> dict | None:
        """★ 在持久化登录会话内执行 GET fetch（复用登录态，供「搜索带单员」等调用）。

        统一走 signal_session 的 _page 上下文，避免 GateScraper 每次新建浏览器
        → 与持久化会话争抢同一 user_data_dir 导致 profile 锁冲突/崩溃。
        - path 含 URL 占位符（如 /detail/{id}）时先自行 format。
        - 返回 JSON dict；未登录/失败返回 None。
        """
        if self._page is None:
            # ★ admin 远程操作期间（独占标志有效）跳过强制拉起：worker 进程此时
            #   启动浏览器会与 admin 的浏览器争抢 user_data_dir（ProcessSingleton 崩溃）。
            if self.admin_hold_active():
                logger.info("gate signal session: fetch_api 跳过（admin 远程操作独占中）")
                return None
            # ★ 会话未启动时自动拉起持久化会话（复用已落盘登录态），避免要求手动先启动。
            #   force_launch=True：即使标记已确认登录也必须真正拉起浏览器，
            #   否则 fetch 需要真实页面会永远失败（worker close 后标记仍为 logged_in）。
            #   ★ 拉起失败重试：双容器共享目录时 worker 侧浏览器可能正持有锁
            #     （TargetClosedError），等待其 60s 轮询周期结束释放后重试。
            logger.info("gate signal session: fetch_api 会话未启动，强制拉起持久化会话")
            await self.start_login(force_launch=True)
            if self._page is None:
                for attempt in range(2):
                    import asyncio as _asyncio

                    await _asyncio.sleep(12)
                    logger.info("gate signal session: fetch_api 拉起重试 %s/2（等待锁释放窗口）", attempt + 1)
                    await self.start_login(force_launch=True)
                    if self._page is not None:
                        break
        if self._page is None:
            logger.warning("gate signal session: fetch_api 无可用页面（强制拉起失败，请检查浏览器/登录态）")
            return None
        # ★ 页面就绪等待：避免页面仍在导航/加载时 evaluate 报 NoneType（高频轮询下必现）
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except Exception:  # noqa: BLE001 页面加载超时/异常不阻断，交给 evaluate 兜底
            pass
        qs = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        url = f"{GATE_BASE}{path}?{qs}" if qs else f"{GATE_BASE}{path}"
        js = (
            f"fetch('{url}',{{headers:{{'Accept':'application/json'}}}})"
            ".then(r=>r.text().then(t=>({s:r.status,t})).catch(()=>({s:0,t:''})))"
        )
        try:
            r = await self._page.evaluate(f"({js})")
            s: int = r.get("s", 0)
            t: str = r.get("t", "")
            if s != 200:
                logger.warning("gate signal session: fetch_api %s -> %s", path, s)
                return None
            data = json.loads(t)
            # ★ 严格校验业务 code：Gate 私有接口未登录时 HTTP 同样可能 200（错误在
            #   body code 里）。★ 成功码两种：多数接口 200，leader/search 等为 0
            #   （2026-08 实测）——其他值视为失败。
            if not isinstance(data, dict) or data.get("code") not in (0, 200):
                logger.warning("gate signal session: fetch_api %s -> biz code %s", path, data.get("code") if isinstance(data, dict) else "?")
                return None
            # ★ 不在此写登录标记：fetch_api 代理的接口多为公开接口（leader 搜索等），
            #   成功不代表登录态。登录判定唯一权威入口是 _check_logged_in（URL+接口双层校验）。
            return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("gate signal session: fetch_api fail %s: %s", path, exc)
            return None

    async def close(self) -> None:
        """关闭浏览器（保留 user_data_dir 登录态，供信号源复用）。"""
        try:
            if self._context:
                await self._context.close()
            elif self._browser:
                await self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        # ★ playwright driver 是独立 node 子进程：不 stop() 会随每次会话泄漏
        pw = self._playwright
        if pw is not None:
            try:
                await pw.stop()
            except Exception:  # noqa: BLE001
                pass
        self._context = None
        self._browser = None
        self._page = None
        self._playwright = None
        self._state = "idle"

    def status(self) -> SessionStatus:
        """当前会话状态。"""
        if self._page is None:
            # ★ 本进程未持有浏览器时，读取跨进程登录态标记（worker 可能在别处持有浏览器）
            marker = self._read_marker()
            if marker.get("logged_in"):
                return SessionStatus(
                    "logged_in",
                    logged_in=True,
                    trader_count=int(marker.get("trader_count") or 0),
                    message=marker.get("message") or "已登录（复用持久化登录态）",
                    has_persisted=True,
                    source_mode="follower",
                )
            return SessionStatus(
                "idle",
                has_persisted=self._has_persisted_dir(),
                source_mode="follower",
            )
        url = ""
        try:
            url = self._page.url
        except Exception:  # noqa: BLE001
            pass
        return SessionStatus(
            self._state,
            logged_in=self._state == "logged_in",
            url=url,
            has_persisted=True,
            source_mode="follower",
        )


# 单例
_session = SignalSession()


def get_signal_session() -> SignalSession:
    return _session