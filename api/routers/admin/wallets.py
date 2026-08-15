# admin/wallets 路由（M5：钱包账本 —— 全平台奖励流水 + 手动补发/扣除，高危写操作强制 audit-log）
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.core.errors import NotFoundError, ValidationError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.billing import PaymentOrder, Reward
from api.models.user import User
from api.services.audit.service import AuditService

router = APIRouter(prefix="/wallets", tags=["admin-wallets"])

STATUS_LABEL = {
    "verifying": "核实中", "available": "已到账", "withdrawing": "提现中",
    "paid": "已提现", "frozen": "冻结", "canceled": "已取消",
    "paid_failed": "发放失败", "rolled_back": "已回滚",
}


class AdjustIn(BaseModel):
    user_id: int
    amount_usdt: float = Field(gt=0)
    reason: str = Field(min_length=2, max_length=128)


@router.get("")
async def ledger(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    """全平台奖励流水明细（★ G12 5 字段账本）。"""
    from sqlalchemy import func, select

    count_stmt = select(func.count(Reward.id))
    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.execute(
            select(Reward, User)
            .join(User, User.id == Reward.owner_id, isouter=True)
            .order_by(Reward.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "owner_id": r.owner_id,
                "owner_email": u.email if u else str(r.owner_id),
                "source_user_id": r.source_user_id,
                "amount_usdt": r.amount_usdt,
                "status": r.status,
                "status_label": STATUS_LABEL.get(r.status, r.status),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r, u in rows
        ],
    }


@router.get("/summary")
async def summary(db: DbDep = None, _admin=Depends(get_current_admin)) -> dict:
    """★ G12 全平台 5 字段汇总：累计/可提现/提现中/已提现/冻结。"""
    from sqlalchemy import select

    rewards = (await db.execute(select(Reward))).scalars().all()
    total = available = withdrawing = paid = frozen = 0.0
    for r in rewards:
        total += r.amount_usdt
        if r.status == "available":
            available += r.amount_usdt
        elif r.status == "withdrawing":
            withdrawing += r.amount_usdt
        elif r.status == "paid":
            paid += r.amount_usdt
        else:
            frozen += r.amount_usdt
    return {
        "total_usdt": round(total, 2),
        "available_usdt": round(available, 2),
        "withdrawing_usdt": round(withdrawing, 2),
        "paid_usdt": round(paid, 2),
        "frozen_usdt": round(frozen, 2),
    }


@router.post("/adjust")
async def adjust(body: AdjustIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """手动补发(+)/扣除(-)：创建 Reward 流水（positive=补发，negative=扣除），必须填理由留痕。"""
    user = await db.get(User, body.user_id)
    if user is None:
        raise NotFoundError("用户不存在")

    # 手工流水需要一个支付订单锚点（FK 约束），此处创建合成订单
    anchor = PaymentOrder(
        user_id=body.user_id,
        plan_id="manual",
        amount_usdt=abs(body.amount_usdt),
        network="trc20",
        status="confirmed",
    )
    db.add(anchor)
    await db.flush()

    reward = Reward(
        owner_id=body.user_id,
        source_user_id=body.user_id,
        source_payment_order_id=anchor.id,
        amount_usdt=body.amount_usdt,
        status="available",
        created_at=datetime.now(timezone.utc),
    )
    db.add(reward)
    await db.commit()

    await AuditService(db).log(
        actor_id=admin["id"],
        action="wallet.adjust",
        target_type="reward", target_id=str(reward.id),
        after={"user_id": body.user_id, "amount_usdt": body.amount_usdt, "status": "available"},
        reason=body.reason,
    )
    return {"id": reward.id, "user_id": body.user_id, "amount_usdt": body.amount_usdt, "status": "available"}