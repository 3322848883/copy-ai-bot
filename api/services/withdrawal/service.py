# withdrawal 模块（M4 T4.6/T4.7：申请锁定 + 审核 5 动作）
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.errors import NotFoundError, ValidationError, WithdrawalError
from api.models.billing import Reward, Withdrawal
from api.services.ledger.service import LedgerService

logger = logging.getLogger("signal-saas.withdrawal")

# ★ G13：最低提现门槛（后台可配，默认 10U）+ 1U 手续费
TRC20_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
BEP20_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class WithdrawalService:
    """提现：申请锁定 → 人工审核 5 动作（approve/reject/fill_tx/retry/refund）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def request(self, user_id: int, network: str, address: str, amount_usdt: float) -> Withdrawal:
        """申请提现：门槛校验 → 地址正则 → 冻结可用余额。"""
        if not self._valid_address(network, address):
            raise ValidationError("收款地址格式错误")
        if amount_usdt < self.settings.withdraw_min_usdt:
            raise WithdrawalError(f"最低提现门槛 {self.settings.withdraw_min_usdt}U")

        ledger = LedgerService(self.db)
        balance = await ledger.balance(user_id)
        available = balance["available_usdt"]
        if amount_usdt > available:
            raise WithdrawalError(f"可提现余额不足：{available}U")

        # 锁定：冻结对应 Reward（available → withdrawing）
        rewards = (
            await self.db.execute(
                select(Reward).where(Reward.owner_id == user_id, Reward.status == "available")
            )
        ).scalars().all()
        to_lock = amount_usdt
        for r in rewards:
            if to_lock <= 0:
                break
            r.status = "withdrawing"
            to_lock = round(to_lock - r.amount_usdt, 2)
        if to_lock > 0:
            raise WithdrawalError("奖励拆分锁定失败，请重试")

        wd = Withdrawal(
            user_id=user_id,
            amount_usdt=amount_usdt,
            fee_usdt=self.settings.withdraw_fee_usdt,
            network=network,
            address=address,
            status="pending_review",
        )
        self.db.add(wd)
        await self.db.commit()
        await self.db.refresh(wd)
        await self._push_status(wd)
        return wd

    def _valid_address(self, network: str, address: str) -> bool:
        if network == "trc20":
            return bool(TRC20_RE.match(address))
        if network == "bep20":
            return bool(BEP20_RE.match(address))
        if network == "erc20":
            return bool(BEP20_RE.match(address))
        return False

    # ── 审核 5 动作 ──
    async def approve(self, withdrawal_id: int, reviewer_id: int) -> Withdrawal:
        wd = await self._get(withdrawal_id)
        if wd.status != "pending_review":
            raise WithdrawalError(f"状态 {wd.status} 不允许审核")
        wd.status = "approved"
        wd.reviewed_by = reviewer_id
        await self.db.commit()
        await self.db.refresh(wd)
        await self._push_status(wd)
        return wd

    async def reject(self, withdrawal_id: int, reviewer_id: int, reason: str) -> Withdrawal:
        """拒绝 → 资金退回 available。"""
        wd = await self._get(withdrawal_id)
        if wd.status != "pending_review":
            raise WithdrawalError(f"状态 {wd.status} 不允许拒绝")
        wd.status = "rejected"
        wd.reject_reason = reason
        wd.reviewed_by = reviewer_id
        await self._release_funds(wd)
        await self.db.commit()
        await self.db.refresh(wd)
        await self._push_status(wd)
        return wd

    async def fill_tx(self, withdrawal_id: int, reviewer_id: int, tx_hash: str) -> Withdrawal:
        """管理员填 TxHash → 链上校验通过 → paid。"""
        wd = await self._get(withdrawal_id)
        if wd.status not in ("approved", "processing"):
            raise WithdrawalError(f"状态 {wd.status} 不允许填 TxHash")
        wd.tx_hash = tx_hash
        # 生产：链上校验 TxHash；dev 校验非空即通过
        if not tx_hash:
            raise WithdrawalError("TxHash 不能为空")
        wd.status = "paid"
        wd.reviewed_by = reviewer_id
        # 奖励状态 withdrawing → paid
        await self._mark_paid(wd)
        await self.db.commit()
        await self.db.refresh(wd)
        await self._push_status(wd)
        return wd

    async def retry(self, withdrawal_id: int) -> Withdrawal:
        """转账失败重试：paid_failed → approved。"""
        wd = await self._get(withdrawal_id)
        if wd.status != "paid_failed":
            raise WithdrawalError("仅 paid_failed 可重试")
        wd.status = "approved"
        await self.db.commit()
        await self.db.refresh(wd)
        await self._push_status(wd)
        return wd

    async def refund(self, withdrawal_id: int) -> Withdrawal:
        """退还 → 资金回退 available。"""
        wd = await self._get(withdrawal_id)
        if wd.status not in ("rejected", "paid_failed"):
            raise WithdrawalError("当前状态不可退还")
        wd.status = "refunded"
        await self._release_funds(wd)
        await self.db.commit()
        await self.db.refresh(wd)
        await self._push_status(wd)
        return wd

    # ── helpers ──
    async def _push_status(self, wd: Withdrawal) -> None:
        """★ M6 P0：实时推送提现状态（withdrawal.status）。"""
        from api.ws.hub import hub

        await hub.push(
            wd.user_id,
            "withdrawal.status",
            {
                "withdrawal_id": wd.id,
                "amount_usdt": wd.amount_usdt,
                "status": wd.status,
                "tx_hash": wd.tx_hash,
                "reject_reason": wd.reject_reason,
            },
        )

    async def _get(self, withdrawal_id: int) -> Withdrawal:
        wd = await self.db.get(Withdrawal, withdrawal_id)
        if wd is None:
            raise NotFoundError("提现单不存在")
        return wd

    async def _release_funds(self, wd: Withdrawal) -> None:
        """拒绝/退还：withdrawing → available。"""
        rewards = (
            await self.db.execute(
                select(Reward).where(
                    Reward.owner_id == wd.user_id,
                    Reward.status == "withdrawing",
                )
            )
        ).scalars().all()
        for r in rewards:
            r.status = "available"

    async def _mark_paid(self, wd: Withdrawal) -> None:
        """发放成功：withdrawing → paid。"""
        rewards = (
            await self.db.execute(
                select(Reward).where(
                    Reward.owner_id == wd.user_id,
                    Reward.status == "withdrawing",
                )
            )
        ).scalars().all()
        for r in rewards:
            r.status = "paid"
