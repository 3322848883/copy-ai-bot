# rewards 路由（M4 T4.5：★ G12 奖励余额 5 字段 + 流水）
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import DbDep, get_current_user
from api.services.ledger.service import LedgerService

router = APIRouter(prefix="/rewards", tags=["rewards"])


@router.get("/balance")
async def balance(db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    """★ G12：累计/可提现/提现中/已提现/冻结 5 字段。"""
    svc = LedgerService(db)
    return await svc.balance(user_id)


@router.get("/ledger")
async def ledger(limit: int = Query(50, ge=1, le=200), db: DbDep = None, user_id: int = Depends(get_current_user)) -> dict:
    svc = LedgerService(db)
    return {"items": await svc.list_ledger(user_id, limit)}
