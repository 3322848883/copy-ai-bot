# ledger 模块（M4 T4.5：奖励流水账；不直接改 user 余额）
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.billing import Reward

logger = logging.getLogger("signal-saas.ledger")


class LedgerService:
    """奖励账本：5 字段（★ G12 累计/可提现/提现中/已提现/冻结）。

    不直接修改 user 余额，全部以 Reward 记录状态推导（设计蓝本 §7）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def balance(self, user_id: int) -> dict:
        """★ G12：奖励余额 5 字段。"""
        rewards = (
            await self.db.execute(select(Reward).where(Reward.owner_id == user_id))
        ).scalars().all()

        total = 0.0          # 累计
        available = 0.0      # 可提现
        withdrawing = 0.0    # 提现中
        paid = 0.0           # 已提现
        frozen = 0.0         # 冻结（verifying/canceled）

        for r in rewards:
            total += r.amount_usdt
            if r.status == "available":
                available += r.amount_usdt
            elif r.status == "withdrawing":
                withdrawing += r.amount_usdt
            elif r.status == "paid":
                paid += r.amount_usdt
            else:
                frozen += r.amount_usdt  # verifying / frozen / canceled / paid_failed / rolled_back

        return {
            "total_usdt": round(total, 2),
            "available_usdt": round(available, 2),
            "withdrawing_usdt": round(withdrawing, 2),
            "paid_usdt": round(paid, 2),
            "frozen_usdt": round(frozen, 2),
        }

    async def list_ledger(self, user_id: int, limit: int = 50) -> list[dict]:
        rewards = (
            await self.db.execute(select(Reward).where(Reward.owner_id == user_id).order_by(Reward.id.desc()).limit(limit))
        ).scalars().all()
        source_ids = {r.source_user_id for r in rewards if r.source_user_id}
        source_emails: dict[int, str] = {}
        if source_ids:
            from api.models.user import User

            rows = (
                await self.db.execute(select(User.id, User.email).where(User.id.in_(source_ids)))
            ).all()
            source_emails = {uid: email for uid, email in rows}
        return [
            {
                "id": r.id,
                "source_user_id": r.source_user_id,
                "source_email": source_emails.get(r.source_user_id) if r.source_user_id else None,
                "amount_usdt": r.amount_usdt,
                "status": r.status,
                "verifying_ends_at": r.verifying_ends_at.isoformat() if r.verifying_ends_at else None,
                "created_at": r.created_at.isoformat() if hasattr(r, "created_at") else None,
            }
            for r in rewards
        ]
