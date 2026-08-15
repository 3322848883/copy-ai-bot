# 模式2 信号源·Gate 登录会话路由（后台管理「登录 Gate」）
from __future__ import annotations

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
async def session_start(_: Any = Depends(get_current_admin)) -> dict:
    """启动持久化浏览器并打开 Gate 登录/跟单页（后台远程操作起点）。"""
    settings = get_settings()
    if not settings.signal_session_enabled:
        raise AuthError("signal_session 功能未启用")
    st = await get_signal_session().start_login()
    return st.__dict__


@router.get("/screenshot")
async def session_screenshot(_: Any = Depends(get_current_admin)) -> Response:
    """返回当前远程浏览器页面 PNG（前端轮询显示，坐标按 1440x900 换算）。"""
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
    return st.__dict__


@router.post("/close")
async def session_close(_: Any = Depends(get_current_admin)) -> dict:
    """关闭浏览器（保留 user_data_dir 登录态，供信号源复用）。"""
    await get_signal_session().close()
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

    scraper = GateScraper(headless=False, mock=False)
    # ★ 复用持久化登录会话的 fetch，避免每次搜索新建浏览器争抢同一 user_data_dir
    fetcher = get_signal_session().fetch_api
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
        pass
    if items is None:
        return {"ok": False, "message": "搜索接口失败或未登录（请先在「登录 Gate」页完成登录）", "items": []}
    return {"ok": True, "keyword": kw, "items": items, "page": page, "page_size": page_size,
            "source": "search"}