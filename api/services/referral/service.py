# referral 模块（M4 T4.5/T4.9：邀请关系 + 刷单检测）
from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.billing import Invite, PaymentOrder, Reward
from api.models.user import Identity, User

logger = logging.getLogger("signal-saas.referral")

# ★ T4.9：1h 内 ≥N 个下级只买试用 → RiskFlag
ABUSE_TRIAL_THRESHOLD = 3
ABUSE_WINDOW_HOURS = 1


class ReferralService:
    """邀请码管理 + 邀请关系查询 + 刷单检测（★ G11/G12 关联）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_code(self, user_id: int) -> str:
        """获取/生成专属邀请码（6 位字母数字）。"""
        identity = (
            await self.db.execute(select(Identity).where(Identity.user_id == user_id))
        ).scalars().first()
        if identity is None:
            identity = Identity(user_id=user_id)
            self.db.add(identity)
        if not identity.invite_code:
            identity.invite_code = self._gen_code()
            await self.db.commit()
        return identity.invite_code

    def _gen_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(6))

    async def list_invites(self, user_id: int) -> list[dict]:
        """邀请列表（含核实倒计时信息）。"""
        invites = (
            await self.db.execute(
                select(Invite).where(Invite.inviter_id == user_id).order_by(Invite.id.desc())
            )
        ).scalars().all()
        out = []
        for inv in invites:
            user = await self.db.get(User, inv.invitee_id)
            rewards = (
                await self.db.execute(select(Reward).where(Reward.source_user_id == inv.invitee_id))
            ).scalars().all()
            total_reward = sum(r.amount_usdt for r in rewards)
            out.append(
                {
                    "invitee_email": user.email if user else str(inv.invitee_id),
                    "code": inv.code,
                    "bound_at": inv.bound_at.isoformat(),
                    "reward_usdt": round(total_reward, 2),
                    "reward_status": rewards[0].status if rewards else "none",
                    "verifying_ends_at": rewards[0].verifying_ends_at.isoformat() if rewards and rewards[0].verifying_ends_at else None,
                }
            )
        return out

    async def get_stats(self, user_id: int) -> dict:
        """M6 前端补全：邀请中心统计卡（累计邀请/累计奖励/待核实/可提现）。"""
        invites = (
            await self.db.execute(
                select(Invite).where(Invite.inviter_id == user_id)
            )
        ).scalars().all()
        invitee_ids = [inv.invitee_id for inv in invites]
        total_invitees = len(invitee_ids)
        total_reward = 0.0
        verifying_reward = 0.0
        available_reward = 0.0
        if invitee_ids:
            rewards = (
                await self.db.execute(
                    select(Reward).where(Reward.source_user_id.in_(invitee_ids))
                )
            ).scalars().all()
            for r in rewards:
                total_reward += r.amount_usdt
                if r.status == "verifying":
                    verifying_reward += r.amount_usdt
                elif r.status == "available":
                    available_reward += r.amount_usdt
        return {
            "total_invitees": total_invitees,
            "total_reward": round(total_reward, 2),
            "verifying_reward": round(verifying_reward, 2),
            "available_reward": round(available_reward, 2),
        }

    async def detect_batch_abuse(self, inviter_id: int) -> bool:
        """★ T4.9：1h 内 ≥3 个下级只买试用 → 标记刷单风险。"""
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=ABUSE_WINDOW_HOURS)
        rows = await self.db.execute(
            select(PaymentOrder.id)
            .join(Invite, Invite.invitee_id == PaymentOrder.user_id)
            .where(
                Invite.inviter_id == inviter_id,
                PaymentOrder.plan_id == "trial_5u",
                PaymentOrder.status == "confirmed",
                PaymentOrder.created_at >= one_hour_ago,
            )
            .distinct()
        )
        return len(rows.scalars().all()) >= ABUSE_TRIAL_THRESHOLD
