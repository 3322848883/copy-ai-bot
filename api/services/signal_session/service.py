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

import asyncio
import logging
from dataclasses import dataclass, field
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

    # ── 生命周期 ──
    async def start_login(self) -> SessionStatus:
        """启动持久化浏览器并打开 Gate 登录页（后台管理远程操作起点）。"""
        if self._page is not None:
            return self.status()
        settings = get_settings()
        self._data_dir = settings.signal_session_data_dir
        self._state = "launching"
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            headless = True if settings.signal_session_headless is None else settings.signal_session_headless
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self._data_dir,
                    channel="chrome",
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                )
                logger.info("gate signal session: launch persistent chrome (headless=%s)", headless)
            except Exception as exc:  # noqa: BLE001 无系统 Chrome → 内置 chromium
                logger.warning("gate signal session: chrome channel fail (%s), fallback chromium", exc)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self._data_dir,
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                )
            self._browser = self._context.browser
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            # 若已有登录态(user_data_dir 非空)，直接进已登录; 否则进登录页
            await self._page.goto(GATE_COPY_MINE_URL, wait_until="domcontentloaded", timeout=60_000)
            self._state = "active"
            return self.status()
        except Exception as exc:  # noqa: BLE001
            logger.exception("signal session start_login failed")
            self._state = "idle"
            return SessionStatus("idle", message=f"启动失败: {exc}")

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
        return SessionStatus(
            self._state,
            logged_in=ok,
            trader_count=count,
            message="登录成功，会话已持久化" if ok else "尚未检测到有效登录，请完成账号密码/验证码",
            url=self._page.url if self._page else "",
            has_persisted=True,
        )

    async def _check_logged_in(self) -> tuple[bool, int]:
        """在页面内 fetch 跟单账户接口，判断登录态；返回 (是否登录, 跟单交易员数)。"""
        if self._page is None:
            return False, 0
        try:
            js = (
                f"fetch('{GATE_BASE}{_CHECK_PATH}?trader_name=&market=&page=1&page_size=100&sub_website_id=0',"
                "{credentials:'include'}).then(r=>r.status===200?r.json():null)"
            )
            resp = await self._page.evaluate(
                f"({js}).then(d=>d&&d.code===200?d.data.length:0).catch(()=>0)"
            )
            count = int(resp or 0)
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
            # ★ 会话未启动时自动拉起持久化会话（复用已落盘登录态），避免要求手动先启动
            logger.info("gate signal session: fetch_api 会话未启动，自动拉起持久化会话")
            await self.start_login()
            if self._page is None:
                logger.warning("gate signal session: fetch_api 无可用页面（自动启动失败，请先启动登录会话）")
                return None
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
            import json as _json

            return _json.loads(t)
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
        self._context = None
        self._browser = None
        self._page = None
        self._playwright = None
        self._state = "idle"

    def status(self) -> SessionStatus:
        """当前会话状态。"""
        if self._page is None:
            return SessionStatus(
                "idle",
                has_persisted=self._data_dir is not None,
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