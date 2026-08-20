# admin/signals 路由（M5 T5.4：策略管理 - 列表/上架/下架/暂停；G04 force 留痕）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.core.errors import NotFoundError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.signal import Strategy, Trader
from api.services.audit.service import AuditService
from api.services.strategies.service import StrategyService, format_display_name

router = APIRouter(prefix="/signals", tags=["admin-signals"])


class StatusIn(BaseModel):
    status: str  # listed / paused / delisted


class GrayIn(BaseModel):
    gray_pct: int  # 0-100


class ForceListIn(BaseModel):
    trader_id: int
    exchange: str = "gate"  # ★ M6 T8：上架策略所属交易所（不再写死 gate）
    display_name: str = ""  # ★ 统一命名标准：昵称（id），后端忽略自定义名
    style: str = "trend"
    risk_rating: str = "mid"
    force: bool = True
    force_reason: str


class ImportIn(BaseModel):
    """★ M6 T8：把带单员加入待选池（进入该交易所审核流水线），不直接建策略/机器人。"""
    exchange: str
    trader_id: str  # 交易所外部带单员 ID（如 Gate leader_id）
    name: str | None = None
    followers: int = 0


# ── 策略级风控（Redis 可配，键 risk:strategy:{id}:*，默认单笔 2000 / 回撤 25%）──
STRATEGY_RISK_DEFAULTS = {
    "max_order_notional": 2000.0,
    "max_drawdown_pct": 25.0,
}

# ★ M6 T8：当前已具备「信号源采集适配器」的交易所（scrapers/adapters 仅实现 gate）
#   其余所（binance/okx/bybit/bitget）只支持人工导入待选池，真正采集待接入。
COLLECTOR_READY_EXCHANGES = {"gate": True}


def _redis():
    from redis import Redis

    from api.core.config import get_settings

    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def get_strategy_risk(strategy_id: int) -> dict:
    """读取某策略级风控配置（未单独配置时返回默认值 + opt=None）。"""
    r = _redis()
    out = {}
    for key, default in STRATEGY_RISK_DEFAULTS.items():
        raw = r.get(f"risk:strategy:{strategy_id}:{key}")
        if raw is None:
            out[key] = default
            out[f"{key}_set"] = False
        else:
            try:
                out[key] = float(raw)
            except ValueError:
                out[key] = default
            out[f"{key}_set"] = True
    return out


@router.get("/pending")
async def pending_list(exchange: str = Query(""), db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """待选池：无 Strategy 的 Trader + 最新画像快照。★ M6 T8：支持按交易所过滤。"""
    from sqlalchemy import select

    from api.models.signal import Trader, TraderProfile

    # 简化：直接查最新画像（join 最新一条）
    stmt = (
        select(Trader)
        .outerjoin(Strategy, Strategy.trader_id == Trader.id)
        .where(Strategy.id.is_(None))
        .order_by(Trader.id.desc())
        .limit(100)
    )
    if exchange:
        stmt = stmt.where(Trader.exchange == exchange.lower())
    items = []
    for trader in (await db.execute(stmt)).scalars().all():
        profile = (
            await db.execute(
                select(TraderProfile)
                .where(TraderProfile.trader_id == trader.id)
                .order_by(TraderProfile.snapshot_date.desc())
                .limit(1)
            )
        ).scalars().first()
        items.append(
            {
                "id": trader.id,
                "exchange": trader.exchange,
                "trader_id": trader.trader_id,
                "name": format_display_name(trader.name, trader.trader_id),
                "roi_7d": profile.roi_7d if profile else 0,
                "roi_30d": profile.roi_30d if profile else 0,
                "roi_all": profile.roi_all if profile else 0,
                "win_rate_all": profile.win_rate_all if profile else 0,
                "max_drawdown": profile.max_drawdown if profile else 0,
                "trading_days": profile.trading_days if profile else 0,
                "followers": trader.followers or 0,
                # ★ 仓位公开状态（Gate is_hide）：True=隐藏（公开采集拿不到仓位，上架只能模式B）
                "hide_position": trader.hide_position,
                # ★ M6 T8：仅 Gate 具备信号源采集适配器，其余所标记“待接入采集”
                "collector_ready": COLLECTOR_READY_EXCHANGES.get(trader.exchange, False),
            }
        )
    # ★ 排序：G04 门槛全部通过在前 → 胜率高 → 回撤低 → 带单天数多
    items.sort(
        key=lambda t: (
            0 if (t["win_rate_all"] >= 55 and t["max_drawdown"] <= 30 and t["trading_days"] >= 30) else 1,
            -t["win_rate_all"],
            t["max_drawdown"],
            -t["trading_days"],
        )
    )
    return {"items": items}


@router.get("")
async def list_strategies(
    status: str = Query(""),
    exchange: str = Query(""),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from datetime import datetime

    from sqlalchemy import select

    from api.models.signal import TraderProfile
    from api.services.scraper.adapters.gate import FOLLOW_ORDER_PATH
    from api.services.signal_session.service import get_signal_session

    # ★ 已跟单 leader_id 集合（复用持久化登录会话，用于「已跟单在前」排序）
    followed_ids: set[str] = set()
    try:
        resp = await get_signal_session().fetch_api(
            FOLLOW_ORDER_PATH,
            {"page": 1, "page_size": 50, "status": "running", "asset": "", "market": ""},
        )
        if resp and resp.get("code") == 200:
            for o in (resp.get("data") or {}).get("orders") or []:
                lid = o.get("leader_id")
                if lid is not None:
                    followed_ids.add(str(lid))
    except Exception:  # noqa: BLE001 会话不可用则全部视为未跟单
        pass

    stmt = select(Strategy).order_by(Strategy.id.desc())
    if status:
        stmt = stmt.where(Strategy.status == status)
    if exchange:
        stmt = stmt.where(Strategy.source_exchange == exchange.lower())
    rows = (await db.execute(stmt)).scalars().all()
    items = []
    for s in rows:
        trader = await db.get(Trader, s.trader_id)
        profile = (
            await db.execute(
                select(TraderProfile)
                .where(TraderProfile.trader_id == s.trader_id)
                .order_by(TraderProfile.snapshot_date.desc())
                .limit(1)
            )
        ).scalars().first()
        risk = get_strategy_risk(s.id)
        items.append(
            {
                "id": s.id,
                "trader_id": s.trader_id,
                "exchange": s.source_exchange,
                "display_name": s.display_name,
                "style": s.style,
                "risk_rating": s.risk_rating,
                "status": s.status,
                "followers": trader.followers if trader else 0,
                # ★ 仓位公开状态（Gate is_hide）：True=隐藏（公开采集拿不到仓位，仅模式B 可跟）
                "hide_position": trader.hide_position if trader else None,
                "roi_7d": profile.roi_7d if profile else 0,
                "roi_30d": profile.roi_30d if profile else 0,
                "roi_all": profile.roi_all if profile else 0,
                "win_rate_30d": profile.win_rate_30d if profile else 0,
                "win_rate_all": profile.win_rate_all if profile else 0,
                "max_drawdown": profile.max_drawdown if profile else 0,
                "trading_days": profile.trading_days if profile else 0,
                # ★ 策略级风控（Redis 可配，opt 为 None 表示未单独配置）
                "risk": risk,
                # ★ M6 T8：采集适配器是否就绪（仅 gate）
                "collector_ready": COLLECTOR_READY_EXCHANGES.get(s.source_exchange, False),
                # ★ 排序：是否我账户已跟单 + 上架时间
                "is_follow": trader is not None and trader.trader_id in followed_ids,
                "created_at": s.created_at,
            }
        )
    # ★ 排序：已跟单在前，同组按最新时间（created_at 新→旧）
    items.sort(key=lambda x: x["created_at"] or datetime.min, reverse=True)
    items.sort(key=lambda x: not x["is_follow"])
    return {"items": items}


@router.post("")
async def force_list(body: ForceListIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ G04：强制上架（跳过门槛，必须填理由留痕 audit-log）。★ M6 T8：按所选交易所透传。"""
    svc = StrategyService(db)
    strategy, gate = await svc.add_strategy(
        trader_id=body.trader_id,
        display_name=body.display_name,
        style=body.style,
        risk_rating=body.risk_rating,
        exchange=(body.exchange or "gate").lower(),
        force=True,
        force_reason=body.force_reason,
        actor_id=admin["id"],
    )
    # ★ M6 T5.19：strategy.update 实时推送
    from api.ws.hub import hub

    await hub.broadcast(
        "strategy.update",
        {"strategy_id": strategy.id, "display_name": strategy.display_name, "status": strategy.status, "action": "listed"},
    )
    return {"id": strategy.id, "status": strategy.status, "gate_passed": True, "forced": True, "failures": gate.failures}


@router.post("/import")
async def import_source(body: ImportIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ M6 T8：设为数据源（进入审核流水线）。

    把交易所外部带单员写入 Trader，使其出现在对应所的【待选池 /signals/pending】，
    由管理员按 G04 门槛审核上架后，用户再创建跟单机器人。不直接建策略/机器人。
    - 若该带单员已有策略（已上架）→ 幂等返回，提示已存在。
    - 仅 Gate 具备采集适配器，其余所标记 collector_ready=false（待接入采集）。
    """
    from sqlalchemy import select

    from api.core.errors import ValidationError
    from api.models.signal import Trader
    from api.services.signalstore.service import SignalStore

    exchange = (body.exchange or "").strip().lower()
    trader_id = (body.trader_id or "").strip()
    if not exchange or not trader_id:
        raise ValidationError("exchange 与 trader_id 必填")
    accepted = set(COLLECTOR_READY_EXCHANGES) | {"binance", "okx", "bybit", "bitget"}
    if exchange not in accepted:
        raise ValidationError(f"不支持的交易所: {exchange}，应在 {sorted(accepted)}")

    existing_strategy = await db.scalar(
        select(Strategy).join(Trader, Trader.id == Strategy.trader_id).where(
            Trader.exchange == exchange, Trader.trader_id == trader_id
        )
    )
    if existing_strategy is not None:
        await AuditService(db).log(
            actor_id=admin["id"], action="signal_source.import",
            target_type="trader", target_id=f"{exchange}:{trader_id}",
            before={}, after={"status": "already_listed", "strategy_id": existing_strategy.id},
        )
        return {"ok": True, "already_listed": True, "strategy_id": existing_strategy.id, "message": "该带单员已上架为策略，无需重复导入"}

    store = SignalStore(db)
    trader = await store.upsert_trader(exchange, trader_id, name=body.name, followers=body.followers)
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="signal_source.import",
        target_type="trader", target_id=f"{exchange}:{trader_id}",
        before={}, after={"trader_id": trader_id, "exchange": exchange, "name": body.name},
    )
    return {
        "ok": True,
        "already_listed": False,
        "id": trader.id,
        "exchange": exchange,
        "trader_id": trader_id,
        "collector_ready": COLLECTOR_READY_EXCHANGES.get(exchange, False),
        "message": f"已加入 {exchange.upper()} 待选池，请在待选池完成审核上架",
    }


@router.patch("/{strategy_id}/status")
async def update_status(strategy_id: int, body: StatusIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    svc = StrategyService(db)
    strategy = await svc.update_status(strategy_id, body.status, actor_id=admin["id"])
    # ★ M6 T5.19：strategy.update 实时推送
    from api.ws.hub import hub

    await hub.broadcast(
        "strategy.update",
        {"strategy_id": strategy.id, "display_name": strategy.display_name, "status": strategy.status, "action": "status"},
    )
    return {"id": strategy.id, "status": strategy.status}


@router.patch("/{strategy_id}/gray")
async def set_gray(strategy_id: int, body: GrayIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ M6 T6.1 灰度发布：设置放量比例（0-100），audit 留痕。"""
    from api.core.errors import ValidationError


    if not 0 <= body.gray_pct <= 100:
        raise ValidationError("gray_pct 必须在 0-100")
    strategy = await db.get(Strategy, strategy_id)
    if strategy is None:
        raise NotFoundError("策略不存在")
    before = strategy.gray_pct
    strategy.gray_pct = body.gray_pct
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="strategy.gray",
        target_type="strategy", target_id=str(strategy_id),
        before={"gray_pct": before}, after={"gray_pct": strategy.gray_pct},
    )
    return {"id": strategy_id, "gray_pct": strategy.gray_pct}


class StrategyRiskIn(BaseModel):
    max_order_notional: float | None = None
    max_drawdown_pct: float | None = None


class SyncIn(BaseModel):
    trader_id: str | None = None  # 指定同步单个带单员；空则全量（后台异步）


@router.post("/sync")
async def sync_profiles(body: SyncIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ 同步画像（后台「同步画像」按钮）：单带单员同步执行；全量投递 Celery 后台。"""
    from api.core.errors import ValidationError

    from api.workers.tasks_profile import run_sync_one_sync

    await AuditService(db).log(
        actor_id=admin["id"], action="strategy.sync_profile",
        target_type="strategy", target_id=body.trader_id or "all",
        after={"trader_id": body.trader_id},
    )
    if body.trader_id:
        try:
            result = await run_sync_one_sync(body.trader_id)
        except Exception as exc:  # noqa: BLE001 单个失败返回原因，不炸接口
            result = {"trader_id": body.trader_id, "updated": False, "reason": str(exc)}
        return {"mode": "one", "result": result}
    # 全量：优先投递 Celery 后台任务；broker 不可用时降级同步执行 top 50
    try:
        from api.workers.celery_app import celery_app

        task = celery_app.send_task("profile.sync_daily", kwargs={"limit": 50})
        return {"mode": "all", "async": True, "task_id": getattr(task, "id", None)}
    except Exception:  # noqa: BLE001 broker 不可用 → 同步降级
        import asyncio

        from api.workers.tasks_profile import run_sync_daily

        count = asyncio.run(run_sync_daily(50))
        return {"mode": "all", "async": False, "count": count, "note": "broker 不可用，已同步降级"}


@router.get("/{strategy_id}/risk")
async def get_risk(strategy_id: int, db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """★ 策略级风控参数（Redis 可配，未配置返回默认值）。"""
    strategy = await db.get(Strategy, strategy_id)
    if strategy is None:
        raise NotFoundError("策略不存在")
    return {"id": strategy_id, **get_strategy_risk(strategy_id)}


@router.patch("/{strategy_id}/risk")
async def set_risk(strategy_id: int, body: StrategyRiskIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """★ 更新策略级风控参数（audit 留痕）。"""
    from api.core.errors import ValidationError

    strategy = await db.get(Strategy, strategy_id)
    if strategy is None:
        raise NotFoundError("策略不存在")
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise ValidationError("至少提供一个参数")
    r = _redis()
    before = get_strategy_risk(strategy_id)
    for key, value in payload.items():
        if key not in STRATEGY_RISK_DEFAULTS:
            raise ValidationError(f"未知参数: {key}")
        if value < 0:
            raise ValidationError(f"{key} 不能为负")
        r.set(f"risk:strategy:{strategy_id}:{key}", str(value))
    await AuditService(db).log(
        actor_id=admin["id"], action="strategy.risk_update",
        target_type="strategy", target_id=str(strategy_id),
        before=before, after=payload,
    )
    return {"id": strategy_id, **get_strategy_risk(strategy_id)}
