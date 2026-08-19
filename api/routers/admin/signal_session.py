# 模式2 信号源·Gate 登录会话路由（后台管理「登录 Gate」）
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from api.core.config import get_settings
from api.core.errors import AuthError
from api.deps import get_current_admin
from api.services.signal_session.service import get_signal_session

router = APIRouter(prefix="/signal-session", tags=["signal-session"])


class LoginEvent(BaseModel):
    type: str
    x: float | None = None
    y: float | None = None
    button: str | None = None
    key: str | None = None
    text: str | None = None
    deltaX: float | None = None
    deltaY: float | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


@router.get("/status")
async def session_status(_: Any = Depends(get_current_admin)) -> dict:
    """模式2 信号源会话状态（idle/launching/active/logged_in + 跟单数）。"""
    settings = get_settings()
    if not settings.signal_session_enabled:
        return {"enabled": False, "message": "signal_session 功能未启用（config: signal_session_enabled）"}
    st = get_signal_session().status()
    return {"enabled": True, **st.__dict__}


@router.post("/start")
async def session_start(force: bool = False, _: Any = Depends(get_current_admin)) -> dict:
    """启动持久化浏览器并打开 Gate 登录/跟单页（后台远程操作起点）。

    ★ 管理员点击「开始登录/重新拉起」必须真正拉起浏览器（force_launch=True），
      否则登录标记存在时直接短路返回 logged_in——远程视图无法打开、无法操作
      Gate 页面完成跟单（登录界面卡死根因）。force 参数保留兜底用途。
    """
    settings = get_settings()
    if not settings.signal_session_enabled:
        raise AuthError("signal_session 功能未启用")
    # ★ 独占标志：admin 远程操作期间 worker 不得拉起浏览器争抢 user_data_dir
    get_signal_session().acquire_admin_hold()
    svc = get_signal_session()
    st = await svc.start_login(force_launch=True)
    # ★ 锁窗口重试：worker 侧浏览器可能正持有 user_data_dir（ProcessSingleton 锁，
    #   TargetClosedError）；设 hold 后 worker 60s 轮询周期结束会释放，等待重试。
    if st.state != "logged_in" and st.state != "active":
        for _ in range(3):
            await asyncio.sleep(10)
            st = await svc.start_login(force_launch=True)
            if st.state in ("logged_in", "active"):
                break
    # ★ enabled 必须随响应返回：前端以 status.enabled 控制核心 UI 渲染，缺省会误判为"功能未启用"整块塌陷
    return {"enabled": True, **st.__dict__}


@router.get("/screenshot")
async def session_screenshot(_: Any = Depends(get_current_admin)) -> Response:
    """返回当前远程浏览器页面 PNG（前端轮询显示，坐标按 1440x900 换算）。

    ★ 截图轮询同时作为独占标志的心跳续期：admin 长时间操作浏览器期间
      worker 不会因 TTL 过期而拉起浏览器争抢 user_data_dir。
    """
    get_signal_session().refresh_admin_hold()
    png = await get_signal_session().screenshot()
    if png is None:
        return Response(status_code=204)
    return Response(content=png, media_type="image/png")


@router.post("/event")
async def session_event(body: LoginEvent, _: Any = Depends(get_current_admin)) -> dict:
    """把后台界面捕获的输入转发到远程浏览器（click/type/press/wheel/navigate...）。"""
    await get_signal_session().dispatch_event(body.to_dict())
    return {"ok": True}


@router.post("/complete")
async def session_complete(_: Any = Depends(get_current_admin)) -> dict:
    """用户完成登录后校验会话有效性并持久化。"""
    settings = get_settings()
    if not settings.signal_session_enabled:
        raise AuthError("signal_session 功能未启用")
    st = await get_signal_session().complete_login()
    # ★ 完全自动：登录后立即把「我账户跟单的交易员」同步为策略广场展示项
    if st.logged_in:
        try:
            from api.workers.tasks_signal import sync_followed_leaders

            await sync_followed_leaders()
        except Exception as exc:  # noqa: BLE001 同步失败不阻断登录确认
            import logging

            logging.getLogger("signal-saas.admin.signal_session").warning(
                "登录后同步已跟单交易员失败: %s", exc
            )
    return {"enabled": True, **st.__dict__}


@router.post("/close")
async def session_close(_: Any = Depends(get_current_admin)) -> dict:
    """关闭浏览器（保留 user_data_dir 登录态，供信号源复用）。"""
    await get_signal_session().close()
    # ★ 释放独占标志：worker 可恢复 signal_session 采集
    get_signal_session().release_admin_hold()
    return {"ok": True}


@router.get("/search")
async def search_leaders(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    _: Any = Depends(get_current_admin),
) -> dict:
    """★ 搜索跟单交易员（只展示，不跟单）：按昵称/ID 查 Gate 带单员画像。

    复用已登录的持久化浏览会话调 Gate 接口。
    仅用于后台人工确认要跟单的对象，不触发任何跟单/下单操作。
    - keyword 为昵称 → 走 /apiw/v2/copy/leader/search 模糊匹配
    - keyword 为纯数字 ID → 走 /api/copytrade/copy_trading/trader/detail/{id} 精确查（★ 兜底）
    """
    settings = get_settings()
    if not settings.signal_session_enabled:
        return {"ok": False, "message": "signal_session 功能未启用", "items": []}
    from api.services.scraper.adapters.gate import GateScraper

    svc = get_signal_session()
    # ★ 远程操作期间（hold 有效）浏览器归 admin 会话所有，搜完不关；
    #   否则搜索会临时拉起浏览器，用完必须关闭——否则常驻占住 user_data_dir，
    #   worker 的定时自动同步（600s 周期）将永远拉不起来（ProcessSingleton 锁）。
    held = svc.admin_hold_active()
    scraper = GateScraper(headless=False, mock=False)
    # ★ 复用持久化登录会话的 fetch，避免每次搜索新建浏览器争抢同一 user_data_dir
    fetcher = svc.fetch_api
    kw = keyword.strip()
    try:
        if kw.isdigit():
            # ★ 按 ID 精确查兜底
            item = await scraper.get_leader_by_id(kw, fetcher=fetcher)
            if item is None:
                return {"ok": False, "message": "按 ID 查询失败或未登录（请先在「登录 Gate」页完成登录）", "items": []}
            return {"ok": True, "keyword": kw, "items": [item], "page": 1, "page_size": 1,
                    "source": "detail"}
        items = await scraper.search_leaders(kw, page, min(page_size, 50), fetcher=fetcher)
    finally:
        if not held:
            try:
                await svc.close()
            except Exception:  # noqa: BLE001
                pass
    if items is None:
        return {"ok": False, "message": "搜索接口失败或未登录（请先在「登录 Gate」页完成登录）", "items": []}
    return {"ok": True, "keyword": kw, "items": items, "page": page, "page_size": page_size,
            "source": "search"}