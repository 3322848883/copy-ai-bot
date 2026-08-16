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

        # 先建提现单拿到 id，再把锁定 Reward 绑定到该单（★ 修复：并发提现互不干扰）
        wd = Withdrawal(
            user_id=user_id,
            amount_usdt=amount_usdt,
            fee_usdt=self.settings.withdraw_fee_usdt,
            network=network,
            address=address,
            status="pending_review",
        )
        self.db.add(wd)
        await self.db.flush()

        # 锁定：冻结对应 Reward（available → withdrawing），绑定 withdrawal_id
        # ★ P0 修复：部分提现时拆分奖励，只锁定本次申请金额，避免整张奖励被吞没
        rewards = (
            await self.db.execute(
                select(Reward).where(Reward.owner_id == user_id, Reward.status == "available")
                .with_for_update()  # ★ 行锁：防并发两笔提现锁定同一张奖励（双花）
            )
        ).scalars().all()
        to_lock = round(amount_usdt, 2)
        for r in rewards:
            if to_lock <= 0:
                break
            if r.amount_usdt <= to_lock:
                r.status = "withdrawing"
                r.withdrawal_id = wd.id
                to_lock = round(to_lock - r.amount_usdt, 2)
            else:
                # 该奖励大于剩余需锁金额 → 拆分：原奖励保留盈余，新奖励绑定本次提现
                split = Reward(
                    owner_id=r.owner_id,
                    source_user_id=r.source_user_id,
                    source_payment_order_id=r.source_payment_order_id,
                    amount_usdt=to_lock,
                    status="withdrawing",
                    withdrawal_id=wd.id,
                )
                self.db.add(split)
                r.amount_usdt = round(r.amount_usdt - to_lock, 2)
                to_lock = 0
        if to_lock > 0:
            await self.db.rollback()
            raise WithdrawalError("奖励拆分锁定失败，请重试")

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
        if not tx_hash:
            raise WithdrawalError("TxHash 不能为空")
        # ★ H7 修复：生产环境链上校验（to=用户提现地址、金额≥提现额），通过才置 paid
        from api.core.config import get_settings

        if get_settings().app_env != "dev":
            from api.services.payment.chain_client import get_chain_client

            client = get_chain_client(wd.network)
            ok, reason = await client.validate_tx(tx_hash, wd.address, wd.amount_usdt)
            if not ok:
                wd.tx_hash = tx_hash
                wd.status = "paid_failed"
                wd.reviewed_by = reviewer_id
                await self.db.commit()
                await self._push_status(wd)
                raise WithdrawalError(f"链上校验未通过（{reason}），已转发放失败待处理")
        wd.tx_hash = tx_hash
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
        """拒绝/退还：释放归属该提现单的 withdrawing 资金 → available。"""
        rewards = (
            await self.db.execute(
                select(Reward).where(
                    Reward.owner_id == wd.user_id,
                    Reward.status == "withdrawing",
                    Reward.withdrawal_id == wd.id,
                )
            )
        ).scalars().all()
        for r in rewards:
            r.status = "available"
            r.withdrawal_id = None

    async def _mark_paid(self, wd: Withdrawal) -> None:
        """发放成功：归属该提现单的 withdrawing 资金 → paid。"""
        rewards = (
            await self.db.execute(
                select(Reward).where(
                    Reward.owner_id == wd.user_id,
                    Reward.status == "withdrawing",
                    Reward.withdrawal_id == wd.id,
                )
            )
        ).scalars().all()
        for r in rewards:
            r.status = "paid"
            r.withdrawal_id = None
