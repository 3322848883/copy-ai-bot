# admin/withdrawals 路由（M4 T4.7：审核 5 动作；写操作强制 audit-log）
from __future__ import annotations


from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.deps import DbDep, get_current_admin, require_admin
from api.services.audit.service import AuditService
from api.services.withdrawal.service import WithdrawalService

router = APIRouter(prefix="/withdrawals", tags=["admin-withdrawals"])


@router.get("")
async def list_withdrawals(
    status: str = Query(""),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    """提现单列表（按状态筛选 + 分页）。"""
    from sqlalchemy import func, select

    from api.models.billing import Withdrawal

    stmt = select(Withdrawal).order_by(Withdrawal.id.desc())
    count_stmt = select(func.count(Withdrawal.id))
    if status:
        stmt = stmt.where(Withdrawal.status == status)
        count_stmt = count_stmt.where(Withdrawal.status == status)
    total = await db.scalar(count_stmt) or 0
    rows = (
        (await db.execute(stmt.offset((page - 1) * size).limit(size)))
        .scalars()
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": w.id,
                "user_id": w.user_id,
                "amount_usdt": w.amount_usdt,
                "fee_usdt": w.fee_usdt,
                "network": w.network,
                "address": w.address,
                "status": w.status,
                "tx_hash": w.tx_hash,
                "reject_reason": w.reject_reason,
                "created_at": w.created_at.isoformat() if hasattr(w, "created_at") else None,
            }
            for w in rows
        ]
    }


class ApproveIn(BaseModel):
    pass


class RejectIn(BaseModel):
    reason: str = Field(min_length=2, max_length=255)


class FillTxIn(BaseModel):
    tx_hash: str = Field(min_length=8, max_length=128)


class ActionIn(BaseModel):
    pass


@router.post("/{withdrawal_id}/approve")
async def approve(withdrawal_id: int, _body: ApproveIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    svc = WithdrawalService(db)
    wd = await svc.approve(withdrawal_id, admin["id"])
    await AuditService(db).log(
        actor_id=admin["id"], action="withdrawal.approve",
        target_type="withdrawal", target_id=str(withdrawal_id),
        after={"status": wd.status},
    )
    return {"id": wd.id, "status": wd.status}


@router.post("/{withdrawal_id}/reject")
async def reject(withdrawal_id: int, body: RejectIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    svc = WithdrawalService(db)
    wd = await svc.reject(withdrawal_id, admin["id"], body.reason)
    await AuditService(db).log(
        actor_id=admin["id"], action="withdrawal.reject",
        target_type="withdrawal", target_id=str(withdrawal_id),
        after={"status": wd.status, "reason": body.reason},
    )
    return {"id": wd.id, "status": wd.status}


@router.post("/{withdrawal_id}/fill-tx")
async def fill_tx(withdrawal_id: int, body: FillTxIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    svc = WithdrawalService(db)
    wd = await svc.fill_tx(withdrawal_id, admin["id"], body.tx_hash)
    await AuditService(db).log(
        actor_id=admin["id"], action="withdrawal.fill_tx",
        target_type="withdrawal", target_id=str(withdrawal_id),
        after={"status": wd.status, "tx_hash": body.tx_hash},
    )
    return {"id": wd.id, "status": wd.status}


@router.post("/{withdrawal_id}/retry")
async def retry(withdrawal_id: int, _body: ActionIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    svc = WithdrawalService(db)
    wd = await svc.retry(withdrawal_id)
    await AuditService(db).log(
        actor_id=admin["id"], action="withdrawal.retry",
        target_type="withdrawal", target_id=str(withdrawal_id),
        after={"status": wd.status},
    )
    return {"id": wd.id, "status": wd.status}


@router.post("/{withdrawal_id}/refund")
async def refund(withdrawal_id: int, _body: ActionIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    svc = WithdrawalService(db)
    wd = await svc.refund(withdrawal_id)
    await AuditService(db).log(
        actor_id=admin["id"], action="withdrawal.refund",
        target_type="withdrawal", target_id=str(withdrawal_id),
        after={"status": wd.status},
    )
    return {"id": wd.id, "status": wd.status}
