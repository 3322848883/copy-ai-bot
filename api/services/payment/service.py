# payment 模块（M4 T4.3/T4.4：即时校验 + 轮询状态机）
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.errors import PaymentError, ValidationError
from api.models.billing import Invite, PaymentOrder, Reward, PlatformAddress
from api.models.user import Identity
from api.services.billing.service import BillingService
from api.services.payment.chain_client import get_chain_client
from api.services.settings import service as settings_svc

logger = logging.getLogger("signal-saas.payment")

# 轮询间隔（分钟）
POLL_INTERVALS_MIN = [1, 5, 10, 20]
MAX_POLL_ATTEMPTS = 6  # 超过 6 次 → manual

# TxHash 格式：TRON = 64 hex；EVM = 0x + 64 hex；Aptos = 64 hex（0x 前缀可选）
_TRON_TX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_EVM_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_APTOS_TX_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


class PaymentService:
    """支付订单状态机：pending → verifying → polling → confirmed/failed/manual/expired。

    ★ G09：to/value/status 三校验 + 三链确认数轮询。
    ★ H4：行锁 + 交易时间窗 + TxHash 重放 + 实际到账落库。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_order(self, user_id: int, plan_id: str, network: str) -> PaymentOrder:
        """创建支付订单（校验套餐限购 + 网络支持）。"""
        billing = BillingService(self.db)
        plan = billing.get_plan(plan_id)
        await billing.can_purchase(user_id, plan_id)
        if network not in ("trc20", "bep20", "erc20", "aptos"):
            raise ValidationError("network 必须为 trc20 / bep20 / erc20 / aptos")

        order = PaymentOrder(
            user_id=user_id,
            plan_id=plan_id,
            amount_usdt=plan["price_usdt"],
            network=network,
            status="pending",
            required_confirmations=settings_svc.get_chain_confirmations().get(network, 12),
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def submit_tx(self, order_id: int, user_id: int, tx_hash: str) -> PaymentOrder:
        """提交 TxHash → 即时校验（to/value/status 三校验）→ verifying。

        ★ H4 加固：
        - 行级锁（FOR UPDATE）串行化并发提交/轮询对同一订单的操作；
        - 交易时间窗校验：tx 上链时间不得早于订单创建 15 分钟（先付后下单容忍），
          拦截"拿链上历史他人付款激活新订单"（平台地址公开可查，纯哈希查重挡不住）。
        """
        # ★ H4-1 行锁：并发双提交 / 与 poll_sweep 竞争时串行化
        order = (
            await self.db.execute(
                select(PaymentOrder).where(PaymentOrder.id == order_id).with_for_update()
            )
        ).scalars().first()
        if order is None or order.user_id != user_id:
            raise PaymentError("订单不存在")
        if order.status not in ("pending", "verifying", "polling"):
            raise PaymentError(f"订单当前状态 {order.status} 不允许提交 TxHash")

        # 生产环境 TxHash 格式预校验（dev mock 不拦截 mock_ 前缀）
        if get_settings().app_env != "dev" and not self._valid_tx_format(order.network, tx_hash):
            raise PaymentError("TxHash 格式不合法")

        # ★ H1 修复：TxHash 重放检查——同一链上转账不可重复激活多个订单
        used = await self.db.scalar(
            select(PaymentOrder.id).where(
                PaymentOrder.tx_hash == tx_hash,
                PaymentOrder.status != "failed",
            ).limit(1)
        )
        if used is not None:
            raise PaymentError("该 TxHash 已被其他订单使用")

        # ★ P1 修复：TTL 内联校验——expire_sweep 间隔最长 2 分钟，归零后提交仍会被接受；
        #   仅拦 pending 态（已提交进入轮询的订单不受 TTL 限制，否则已付款资金会变死单）
        ttl_min = int(settings_svc.get_rule("payment_order_ttl_min") or 30)
        if (
            order.status == "pending"
            and order.created_at
            and (datetime.now(timezone.utc) - order.created_at).total_seconds() > ttl_min * 60
        ):
            order.status = "expired"
            await self.db.commit()
            raise PaymentError("订单已超时关闭，请重新下单")

        order.tx_hash = tx_hash
        client = get_chain_client(order.network)

        # ★ H4-2 时间窗：tx 上链时间 ≥ 订单创建时间 - 15min。
        #   下单后任意晚支付不受限（订单 TTL 30min）；本窗只拦"先付后下单"超过 15 分钟
        #   及链上历史他人付款（交易所提现到账常需数分钟，15min 覆盖先付款再建单的用户）。
        tx_ts = await client.get_tx_timestamp(tx_hash)
        if tx_ts is not None:
            created_ts = order.created_at.timestamp() if order.created_at else 0
            if tx_ts < created_ts - 900:
                raise PaymentError("该交易早于订单创建时间超过 15 分钟，请重新下单")
            if tx_ts > time.time() + 300:
                raise PaymentError("交易时间异常，请稍后重试")

        # ★ P0 修复：先取链上状态三态分流——未上链 / RPC 故障一律转 verifying 轮询，
        #   绝不在"链上还看不到交易"时做金额判定。此前 _verify_value 在此处把
        #   "已广播未打包"（ETH/BSC 打包需数秒~分钟，用户转账后立即提交是常见时序）
        #   和 RPC 抖动误判为 failed，且 failed 无任何恢复路径（用户不能重提交、
        #   管理员 manual_set 不收 failed），真实到账资金变死单。
        exists, confirmations, meta = await client.get_confirmations(tx_hash)
        order.confirmations = confirmations
        if meta.get("error") == "failed":
            order.status = "failed"
            await self.db.commit()
            raise PaymentError("链上交易回执失败")

        if not exists:
            # 未上链 / RPC 故障 → 转轮询；to/value 待上链后由 poll_order 补校验
            order.status = "verifying"
            await self.db.commit()
            await self.db.refresh(order)
            return order

        # ★ G09 即时校验（交易已上链，结论确定）：to/value 三校验
        to_ok, to_reason = await self._verify_to(order)
        if not to_ok:
            order.status = "failed"
            await self.db.commit()
            raise PaymentError(f"收款地址校验失败: {to_reason}")
        value_ok, value_received = await self._verify_value(order, client)
        if value_ok and value_received is not None:
            # 实际到账金额精确落库（超付可见/可对账；校验语义仍为足额即认）
            order.paid_amount_usdt = value_received
        if not value_ok:
            order.status = "failed"
            await self.db.commit()
            raise PaymentError("到账金额不足")

        if confirmations >= order.required_confirmations:
            await self._confirm(order)
        else:
            # 确认数不足 → 转轮询
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
        if meta.get("error") == "failed":
            order.status = "failed"  # 链上回执明确失败 → 判死
            await self.db.commit()
            return order
        if not exists:
            # 未上链 / RPC 故障 → 继续轮询（不判死），由 attempts 超限兜底转 manual
            order.status = "polling"
            await self.db.commit()
            return order
        if confirmations >= order.required_confirmations:
            # ★ P0 配套：提交时未上链而跳过 to/value 校验的订单，确认前补校验
            #   （paid_amount_usdt 为空 ⟺ 金额校验尚未完成），防止绕过金额校验直接确认
            if order.paid_amount_usdt is None:
                to_ok, to_reason = await self._verify_to(order)
                if not to_ok:
                    order.status = "failed"
                    await self.db.commit()
                    return order
                value_ok, value_received = await self._verify_value(order, get_chain_client(order.network))
                if value_ok and value_received is not None:
                    order.paid_amount_usdt = value_received
                if not value_ok:
                    order.status = "failed"
                    await self.db.commit()
                    return order
            await self._confirm(order)
        else:
            order.status = "polling"
            await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _confirm(self, order: PaymentOrder) -> None:
        """确认支付（★ H3 修复：原子 CAS 幂等——仅首个执行者生效）。"""
        from sqlalchemy import update

        result = await self.db.execute(
            update(PaymentOrder)
            .where(
                PaymentOrder.id == order.id,
                PaymentOrder.status.in_(["pending", "verifying", "polling"]),
            )
            .values(status="confirmed", confirmations=order.required_confirmations)
        )
        if result.rowcount == 0:
            return  # 已被其他路径确认，幂等退出
        await self.db.commit()
        billing = BillingService(self.db)
        await billing.activate_subscription(order.user_id, order.plan_id, order.id)
        await self._trigger_rewards(order)

    async def _trigger_rewards(self, order: PaymentOrder) -> None:
        """按 Invite 关系给邀请人发奖励（★ G11：核实期可配置）。"""
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
        # ★ H3 修复：奖励幂等查重（同一订单只发一次奖励）
        existing_reward = await self.db.scalar(
            select(Reward.id).where(Reward.source_payment_order_id == order.id)
        )
        if existing_reward is not None:
            return
        # ★ G11：风控延长核实期（referral_verify_hours 默认 24h / 风控 referral_abuse_verify_hours 默认 48h）
        # ★ P1 修复：命中风控时以 frozen 状态落库——此前恒写 verifying，前台"冻结奖励"卡永远为 0
        verifying_hours, risk_hit = await self._check_risk_extension(invite.inviter_id)
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        reward_pct = float(settings_svc.get_rule("referral_reward_pct") or 10.0)
        reward = Reward(
            owner_id=invite.inviter_id,
            source_user_id=order.user_id,
            source_payment_order_id=order.id,
            amount_usdt=round(order.amount_usdt * reward_pct / 100.0, 2),
            status="frozen" if risk_hit else "verifying",
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

    async def _check_risk_extension(self, inviter_id: int) -> tuple[int, bool]:
        """★ G11：1h 内 ≥阈值 个下级只买试用 → 风控延长核实期；否则正常核实期。

        返回 (核实小时数, 是否命中风控)——命中时奖励以 frozen 状态落库（前台冻结卡真实展示）。
        """
        from datetime import timedelta

        threshold = int(settings_svc.get_rule("referral_abuse_trial_threshold") or 3)
        normal_hours = int(settings_svc.get_rule("referral_verify_hours") or 24)
        abuse_hours = int(settings_svc.get_rule("referral_abuse_verify_hours") or 48)
        # 动态获取所有试用套餐 plan_id（后台可增删套餐）
        trial_plans = [p["plan_id"] for p in settings_svc.get_plans() if p.get("trial")]
        if not trial_plans:
            return normal_hours, False

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        rows = await self.db.execute(
            select(PaymentOrder.id)
            .join(Invite, Invite.invitee_id == PaymentOrder.user_id)
            .where(
                Invite.inviter_id == inviter_id,
                PaymentOrder.plan_id.in_(trial_plans),
                PaymentOrder.created_at >= one_hour_ago,
            )
            .distinct()
        )
        trial_count = len(rows.scalars().all())
        if trial_count >= threshold:
            return abuse_hours, True
        return normal_hours, False

    # ── ★ G09 三校验 ──
    @staticmethod
    def _valid_tx_format(network: str, tx_hash: str) -> bool:
        """TxHash 格式校验：TRON=64 hex；EVM=0x+64 hex；Aptos=64 hex（0x 可选）。"""
        if network == "trc20":
            return bool(_TRON_TX_RE.match(tx_hash))
        if network == "aptos":
            return bool(_APTOS_TX_RE.match(tx_hash))
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

    async def _verify_value(self, order: PaymentOrder, client) -> tuple[bool, float | None]:
        """校验到账金额 ≥ 下限，返回 (ok, 实际到账USDT)。

        下限 = max(订单金额 - 手续费容差, 订单金额 × 50%)：
        - 容差覆盖交易所提现从本金扣费导致的短付（2026 实测：OKX TRC20 ~1.8U 最高、
          币安 TRC20 ~1.0U、BEP20 ~0.3U、Aptos ~0.04U；默认 2U 全覆盖非 ERC20）；
        - 50% 下限防小额订单被极低金额激活（1U 订单下限 0.5U）；
        - 冷钱包直转 gas 用 TRX/BNB/ETH/APT 另付、USDT 全额到账，不依赖容差。
        """
        try:
            expected_to = getattr(self, "_platform_address", "")
            tol = float(settings_svc.get_rule("payment_fee_tolerance_usdt") or 2.0)
            floor = max(order.amount_usdt - tol, order.amount_usdt * 0.5)
            ok, reason, received = await client.validate_tx(order.tx_hash, expected_to, floor)
            return ok, received
        except Exception:  # noqa: BLE001
            return False, None
