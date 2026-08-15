# payment 模块（M4 T4.3/T4.4：即时校验 + 轮询状态机）
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.errors import PaymentError, ValidationError
from api.models.billing import Invite, PaymentOrder, Reward, PlatformAddress
from api.models.user import Identity
from api.services.billing.service import BillingService
from api.services.payment.chain_client import REQUIRED_CONFIRMATIONS, get_chain_client

logger = logging.getLogger("signal-saas.payment")

# 轮询间隔（分钟）
POLL_INTERVALS_MIN = [1, 5, 10, 20]
MAX_POLL_ATTEMPTS = 6  # 超过 6 次 → manual

# TxHash 格式：TRON = 64 hex；EVM = 0x + 64 hex
_TRON_TX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_EVM_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


class PaymentService:
    """支付订单状态机：pending → verifying → polling → confirmed/failed/manual/timeout。

    ★ G09：to/value/status 三校验 + 三链确认数轮询。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_order(self, user_id: int, plan_id: str, network: str) -> PaymentOrder:
        """创建支付订单（校验套餐限购 + 网络支持）。"""
        billing = BillingService(self.db)
        plan = billing.get_plan(plan_id)
        await billing.can_purchase(user_id, plan_id)
        if network not in ("trc20", "bep20", "erc20"):
            raise ValidationError("network 必须为 trc20 / bep20 / erc20")

        order = PaymentOrder(
            user_id=user_id,
            plan_id=plan_id,
            amount_usdt=plan["price_usdt"],
            network=network,
            status="pending",
            required_confirmations=REQUIRED_CONFIRMATIONS[network],
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def submit_tx(self, order_id: int, user_id: int, tx_hash: str) -> PaymentOrder:
        """提交 TxHash → 即时校验（to/value/status 三校验）→ verifying。"""
        order = await self.db.get(PaymentOrder, order_id)
        if order is None or order.user_id != user_id:
            raise PaymentError("订单不存在")
        if order.status not in ("pending", "verifying", "polling"):
            raise PaymentError(f"订单当前状态 {order.status} 不允许提交 TxHash")

        order.tx_hash = tx_hash
        client = get_chain_client(order.network)

        # 生产环境 TxHash 格式预校验（dev mock 不拦截 mock_ 前缀）
        if get_settings().app_env != "dev" and not self._valid_tx_format(order.network, tx_hash):
            raise PaymentError("TxHash 格式不合法")

        # ★ G09 即时校验：to/value/status 三校验（任一失败拒绝）
        to_ok, to_reason = await self._verify_to(order)
        if not to_ok:
            order.status = "failed"
            await self.db.commit()
            raise PaymentError(f"收款地址校验失败: {to_reason}")
        value_ok = await self._verify_value(order, client)
        if not value_ok:
            order.status = "failed"
            await self.db.commit()
            raise PaymentError("到账金额不足")
        status_ok = await self._verify_tx_status(order, client)
        if not status_ok:
            order.status = "failed"
            await self.db.commit()
            raise PaymentError("交易状态异常")

        # 即时确认数判断
        exists, confirmations, meta = await client.get_confirmations(tx_hash)
        order.confirmations = confirmations
        if exists and confirmations >= order.required_confirmations:
            await self._confirm(order)
        else:
            order.status = "verifying"
            await self.db.commit()
        await self.db.refresh(order)
        return order

    async def poll_order(self, order_id: int) -> PaymentOrder:
        """轮询确认数（Celery Beat 调度 1/5/10/20 min）。"""
        order = await self.db.get(PaymentOrder, order_id)
        if order is None or order.status not in ("verifying", "polling"):
            return order  # 非轮询态直接返回

        order.poll_attempts += 1
        # ★ M6 T6.2 指标：支付轮询次数（按网络）
        try:
            from api.core import metrics as M

            M.payment_poll_attempts_total.labels(network=order.network).inc()
        except Exception:  # noqa: BLE001
            pass
        if order.poll_attempts > MAX_POLL_ATTEMPTS:
            order.status = "manual"  # 超 6 次 → manual
            await self.db.commit()
            return order

        client = get_chain_client(order.network)
        try:
            exists, confirmations, meta = await client.get_confirmations(order.tx_hash)
        except Exception:  # noqa: BLE001
            order.status = "manual"  # API 连续错 → manual
            await self.db.commit()
            return order
        order.confirmations = confirmations
        if not exists:
            order.status = "failed"
            await self.db.commit()
            return order
        if confirmations >= order.required_confirmations:
            await self._confirm(order)
        else:
            order.status = "polling"
            await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _confirm(self, order: PaymentOrder) -> None:
        """确认支付：状态 confirmed → 激活订阅 → 触发奖励。"""
        order.status = "confirmed"
        order.confirmations = order.required_confirmations
        await self.db.commit()
        billing = BillingService(self.db)
        await billing.activate_subscription(order.user_id, order.plan_id, order.id)
        await self._trigger_rewards(order)

    async def _trigger_rewards(self, order: PaymentOrder) -> None:
        """按 Invite 关系给邀请人发 10% 奖励（★ G11：24h 核实期）。"""
        identity = (
            await self.db.execute(select(Identity).where(Identity.user_id == order.user_id))
        ).scalars().first()
        if identity is None or not identity.invite_code:
            return
        invite = (
            await self.db.execute(select(Invite).where(Invite.invitee_id == order.user_id))
        ).scalars().first()
        if invite is None:
            return
        # ★ G11：48h 风控延长（detect_batch_abuse → verifying_hours=48）
        verifying_hours = await self._check_risk_extension(invite.inviter_id)
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        reward = Reward(
            owner_id=invite.inviter_id,
            source_user_id=order.user_id,
            source_payment_order_id=order.id,
            amount_usdt=round(order.amount_usdt * 0.10, 2),
            status="verifying",
            verifying_started_at=now,
            verifying_ends_at=now + timedelta(hours=verifying_hours),
        )
        self.db.add(reward)
        await self.db.commit()
        # ★ M6 P0：实时推送奖励到账（reward.tick，含 24h 倒计时）
        from api.ws.hub import hub

        await hub.push(
            invite.inviter_id,
            "reward.tick",
            {
                "reward_id": reward.id,
                "amount_usdt": reward.amount_usdt,
                "status": reward.status,
                "verifying_ends_at": reward.verifying_ends_at.isoformat() if reward.verifying_ends_at else None,
            },
        )
        # ★ M6 T5.19：account.balance 余额变动推送
        try:
            await hub.push(invite.inviter_id, "account.balance", {"event": "reward_pending", "amount_usdt": reward.amount_usdt})
        except Exception:  # noqa: BLE001
            pass

    async def _check_risk_extension(self, inviter_id: int) -> int:
        """★ G11：1h 内 ≥3 个下级只买试用 → 48h 风控延长；否则 24h。"""
        from datetime import timedelta

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        rows = await self.db.execute(
            select(PaymentOrder.id)
            .join(Invite, Invite.invitee_id == PaymentOrder.user_id)
            .where(
                Invite.inviter_id == inviter_id,
                PaymentOrder.plan_id == "trial_5u",
                PaymentOrder.created_at >= one_hour_ago,
            )
            .distinct()
        )
        trial_count = len(rows.scalars().all())
        return 48 if trial_count >= 3 else 24

    # ── ★ G09 三校验 ──
    @staticmethod
    def _valid_tx_format(network: str, tx_hash: str) -> bool:
        """TxHash 格式校验：TRON=64 hex；EVM=0x+64 hex。"""
        if network == "trc20":
            return bool(_TRON_TX_RE.match(tx_hash))
        return bool(_EVM_TX_RE.match(tx_hash))

    async def _verify_to(self, order: PaymentOrder) -> tuple[bool, str]:
        """校验收款方：从 DB 读取该链 active 平台地址，与链上 to 比对。"""
        addr = (
            await self.db.execute(
                select(PlatformAddress)
                .where(
                    PlatformAddress.network == order.network,
                    PlatformAddress.status == "active",
                )
                .order_by(PlatformAddress.id.desc())
                .limit(1)
            )
        ).scalars().first()
        if addr is None:
            return False, f"{order.network} 网络未配置收款地址"
        self._platform_address = addr.address
        return True, ""

    async def _verify_value(self, order: PaymentOrder, client) -> bool:
        """校验到账金额 ≥ 订单金额（收款方为该链 active 平台地址）。"""
        try:
            expected_to = getattr(self, "_platform_address", "")
            ok, reason = await client.validate_tx(order.tx_hash, expected_to, order.amount_usdt)
            return ok
        except Exception:  # noqa: BLE001
            return False

    async def _verify_tx_status(self, order: PaymentOrder, client) -> bool:
        """校验交易状态（success）。"""
        try:
            exists, _, _ = await client.get_confirmations(order.tx_hash)
            return exists
        except Exception:  # noqa: BLE001
            return False
