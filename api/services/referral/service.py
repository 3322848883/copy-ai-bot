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
from api.services.settings import service as settings_svc

logger = logging.getLogger("signal-saas.referral")

# ★ T4.9：1h 内 ≥N 个下级只买试用 → RiskFlag（阈值后台可配置）
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
        """邀请列表（含核实倒计时信息）。

        ★ P1 修复：reward_status/verifying_ends_at 取该下级**最新一笔**奖励（原取最早一笔，
        多次订阅时金额与状态错配）；奖励查询同时限定 owner_id，避免异常数据串户。
        """
        invites = (
            await self.db.execute(select(Invite).where(Invite.inviter_id == user_id).order_by(Invite.id.desc()))
        ).scalars().all()
        out = []
        for inv in invites:
            user = await self.db.get(User, inv.invitee_id)
            rewards = (
                await self.db.execute(
                    select(Reward)
                    .where(Reward.source_user_id == inv.invitee_id, Reward.owner_id == user_id)
                    .order_by(Reward.id.desc())
                )
            ).scalars().all()
            total_reward = sum(r.amount_usdt for r in rewards)
            latest_reward = rewards[0] if rewards else None
            out.append(
                {
                    "invitee_email": user.email if user else str(inv.invitee_id),
                    "code": inv.code,
                    "bound_at": inv.bound_at.isoformat(),
                    "reward_usdt": round(total_reward, 2),
                    "reward_status": latest_reward.status if latest_reward else "none",
                    "verifying_ends_at": latest_reward.verifying_ends_at.isoformat() if latest_reward and latest_reward.verifying_ends_at else None,
                }
            )
        return out

    async def get_stats(self, user_id: int) -> dict:
        """邀请中心统计卡（★ P1 修复：按 Reward 状态精确聚合，口径与奖励账本页一致）。

        此前前端按每个下级"最早一笔奖励的状态 × 全部金额"推导统计，
        同一下级多次订阅时"已提现/待核实/冻结"互相错配。
        """
        invites = (
            await self.db.execute(select(Invite.id).where(Invite.inviter_id == user_id))
        ).scalars().all()
        total_invitees = len(invites)
        total_reward = verifying_reward = frozen_reward = available_reward = withdrawn_reward = 0.0
        rewards = (
            await self.db.execute(select(Reward).where(Reward.owner_id == user_id))
        ).scalars().all()
        for r in rewards:
            total_reward += r.amount_usdt
            if r.status == "verifying":
                verifying_reward += r.amount_usdt
            elif r.status == "frozen":
                frozen_reward += r.amount_usdt
            elif r.status == "available":
                available_reward += r.amount_usdt
            elif r.status in ("withdrawing", "paid"):
                withdrawn_reward += r.amount_usdt
        return {
            "total_invitees": total_invitees,
            "total_reward": round(total_reward, 2),
            "verifying_reward": round(verifying_reward, 2),
            "frozen_reward": round(frozen_reward, 2),
            "available_reward": round(available_reward, 2),
            "withdrawn_reward": round(withdrawn_reward, 2),
        }

    async def detect_batch_abuse(self, inviter_id: int) -> bool:
        """★ T4.9：1h 内 ≥阈值 个下级只买试用 → 标记刷单风险（参数后台可配置）。"""
        threshold = int(settings_svc.get_rule("referral_abuse_trial_threshold") or 3)
        trial_plans = [p["plan_id"] for p in settings_svc.get_plans() if p.get("trial")]
        if not trial_plans:
            return False
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=ABUSE_WINDOW_HOURS)
        rows = await self.db.execute(
            select(PaymentOrder.id)
            .join(Invite, Invite.invitee_id == PaymentOrder.user_id)
            .where(
                Invite.inviter_id == inviter_id,
                PaymentOrder.plan_id.in_(trial_plans),
                PaymentOrder.status == "confirmed",
                PaymentOrder.created_at >= one_hour_ago,
            )
            .distinct()
        )
        return len(rows.scalars().all()) >= threshold
