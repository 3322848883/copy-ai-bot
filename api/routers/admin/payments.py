# admin/payments 路由（M5 T5.6：支付订单列表 + manual 手动确认/标记失败 + 平台收款地址管理）
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.core.errors import NotFoundError, PaymentError, ValidationError
from api.deps import DbDep, get_current_admin, require_admin
from api.models.billing import PaymentOrder, PlatformAddress
from api.services.audit.service import AuditService

router = APIRouter(prefix="/payments", tags=["admin-payments"])


class ManualIn(BaseModel):
    status: Literal["confirmed", "failed"]


class AddressIn(BaseModel):
    network: str
    address: str
    remark: str | None = None


class AddressPatchIn(BaseModel):
    status: str | None = None  # active / inactive
    remark: str | None = None


# ── 地址格式校验 ──
_TRC20_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
# APTOS：32 字节地址，canonical 形式 0x + 变长 hex（去前导 0），范围 1~64 位
_APTOS_RE = re.compile(r"^0x[0-9a-fA-F]{1,64}$")


def _validate_address(network: str, address: str) -> None:
    if network not in ("trc20", "bep20", "erc20", "aptos"):
        raise ValidationError("network 必须为 trc20 / bep20 / erc20 / aptos")
    if network == "trc20":
        if not _TRC20_RE.match(address):
            raise ValidationError("TRC-20 地址必须为 T 开头 34 位 Base58")
    elif network == "aptos":
        if not _APTOS_RE.match(address):
            raise ValidationError("APTOS 地址必须为 0x + 1~64 位 hex")
    else:
        if not _EVM_RE.match(address):
            raise ValidationError("BEP-20/ERC-20 地址必须为 0x + 40 位 hex")


@router.get("/addresses")
async def list_addresses(
    network: str = Query(""),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from sqlalchemy import select

    stmt = select(PlatformAddress)
    if network:
        stmt = stmt.where(PlatformAddress.network == network)
    rows = (await db.execute(stmt.order_by(PlatformAddress.id.desc()))).scalars().all()
    return {
        "items": [
            {
                "id": a.id,
                "network": a.network,
                "address": a.address,
                "status": a.status,
                "remark": a.remark,
                "updated_by": a.updated_by,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ]
    }


@router.post("/addresses", status_code=201)
async def create_address(body: AddressIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """新增平台收款地址（写操作审计；同一网络仅保留 1 个 active）。"""
    from sqlalchemy import update

    _validate_address(body.network, body.address)
    # ★ M1 修复：同一网络仅允许 1 个 active 收款地址（切换时先停用旧地址，避免校验歧义）
    await db.execute(
        update(PlatformAddress)
        .where(PlatformAddress.network == body.network, PlatformAddress.status == "active")
        .values(status="inactive")
    )
    addr = PlatformAddress(
        network=body.network,
        address=body.address,
        status="active",
        remark=body.remark,
        updated_by=admin["id"],
    )
    db.add(addr)
    await db.commit()
    await db.refresh(addr)
    await AuditService(db).log(
        actor_id=admin["id"], action="payment.address.create",
        target_type="platform_address", target_id=str(addr.id),
        before=None,
        after={"network": addr.network, "address": addr.address},
    )
    return {
        "id": addr.id,
        "network": addr.network,
        "address": addr.address,
        "status": addr.status,
        "remark": addr.remark,
        "note": "同网络旧地址已自动停用",
    }


@router.patch("/addresses/{address_id}")
async def patch_address(address_id: int, body: AddressPatchIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """启停用 / 改备注（写操作审计）。"""
    addr = await db.get(PlatformAddress, address_id)
    if addr is None:
        raise NotFoundError("收款地址不存在")
    if body.status is not None and body.status not in ("active", "inactive"):
        raise ValidationError("status 必须为 active / inactive")
    before = {"status": addr.status, "remark": addr.remark}
    if body.status is not None:
        addr.status = body.status
    if body.remark is not None:
        addr.remark = body.remark
    addr.updated_by = admin["id"]
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="payment.address.update",
        target_type="platform_address", target_id=str(addr.id),
        before=before, after={"status": addr.status, "remark": addr.remark},
    )
    return {"id": addr.id, "status": addr.status, "remark": addr.remark}


@router.delete("/addresses/{address_id}")
async def delete_address(address_id: int, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """删除收款地址（写操作审计）。"""
    addr = await db.get(PlatformAddress, address_id)
    if addr is None:
        raise NotFoundError("收款地址不存在")
    before = {"network": addr.network, "address": addr.address}
    await db.delete(addr)
    await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action="payment.address.delete",
        target_type="platform_address", target_id=str(address_id),
        before=before, after=None,
    )
    return {"ok": True, "id": address_id}


@router.get("")
async def list_orders(
    status: str = Query(""),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbDep = None,
    _admin=Depends(get_current_admin),
) -> dict:
    from sqlalchemy import func, select

    stmt = select(PaymentOrder)
    count_stmt = select(func.count(PaymentOrder.id))
    if status:
        stmt = stmt.where(PaymentOrder.status == status)
        count_stmt = count_stmt.where(PaymentOrder.status == status)
    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.execute(stmt.order_by(PaymentOrder.id.desc()).offset((page - 1) * size).limit(size))
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": o.id,
                "user_id": o.user_id,
                "plan_id": o.plan_id,
                "amount_usdt": o.amount_usdt,
                "network": o.network,
                "tx_hash": o.tx_hash,
                "status": o.status,
                "confirmations": o.confirmations,
                "required": o.required_confirmations,
                "poll_attempts": o.poll_attempts,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in rows
        ],
    }


@router.post("/{order_id}/manual")
async def manual_set(order_id: int, body: ManualIn, db: DbDep = None, admin=Depends(require_admin)) -> dict:
    """manual/verifying 超限订单：人工确认或标记失败。"""
    from sqlalchemy import select

    from api.services.billing.service import BillingService
    from api.services.payment.service import PaymentService

    # ★ P1 修复：行锁 + 状态 CAS——两名管理员并发点击（或与 poll/expire sweep 竞争）时，
    #   仅首个事务能命中状态条件；此后 activate_subscription 非幂等（重复调用重复延长订阅），
    #   并发双确认会双倍延期 + 双发邀请奖励（真金白银），必须由数据库层挡住
    allowed = ("manual", "verifying", "polling", "timeout", "failed", "expired")
    result = await db.execute(
        select(PaymentOrder)
        .where(PaymentOrder.id == order_id, PaymentOrder.status.in_(allowed))
        .with_for_update()
    )
    order = result.scalars().first()
    if order is None:
        exists = await db.get(PaymentOrder, order_id)
        if exists is None:
            raise NotFoundError("订单不存在")
        raise PaymentError(f"订单状态 {exists.status} 不可人工处理")

    before = order.status
    if body.status == "confirmed":
        # ★ L2 修复：人工确认同步确认数，避免列表展示 0/32 的矛盾
        order.status = "confirmed"
        order.confirmations = order.required_confirmations
        await db.commit()
        billing = BillingService(db)
        await billing.activate_subscription(order.user_id, order.plan_id, order.id)
        svc = PaymentService(db)
        await svc._trigger_rewards(order)
    else:
        order.status = "failed"
        await db.commit()
    await AuditService(db).log(
        actor_id=admin["id"], action=f"payment.manual_{body.status}",
        target_type="payment", target_id=str(order_id),
        before={"status": before}, after={"status": order.status},
    )
    return {"id": order_id, "status": order.status}
