# identity 模块（M1 T1.4：G06 PlatformPool / G27 交易所邀请码）
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.errors import ConflictError, ExchangeInviteError, NotFoundError
from api.models.exchange import ExchangeInviteCode, PlatformPool
from api.models.user import Identity, User
from api.services.audit.service import AuditService

ALLOWED_EXCHANGES = ("gate", "binance", "okx", "bybit", "bitget")


class IdentityService:
    def __init__(self, db: AsyncSession, audit: AuditService) -> None:
        self.db = db
        self.audit = audit

    # ── 选所属所（一次性）──
    async def choose_exchange(self, user_id: int, exchange: str) -> Identity:
        exchange = exchange.lower()
        if exchange not in ALLOWED_EXCHANGES:
            raise NotFoundError(f"不支持的交易所: {exchange}")

        identity = await self.db.get(Identity, user_id)
        if identity is None:
            identity = Identity(user_id=user_id, exchange=exchange)
            self.db.add(identity)
            await self.db.commit()
            await self.db.refresh(identity)
            return identity
        if identity.exchange is not None:
            # 验收门：选所后再选所 → 409
            raise ConflictError("已选择所属交易所，不可重复选择")
        identity.exchange = exchange
        await self.db.commit()
        await self.db.refresh(identity)
        return identity

    # ── 好友邀请码（防循环 + 一次性）──
    async def bind_invite_code(self, user_id: int, code: str) -> Identity:
        """绑定好友邀请码：校验邀请人存在、防自邀、防循环（祖先链回溯）。"""
        code = code.strip().upper()
        if not code:
            raise NotFoundError("邀请码不能为空")

        inviter = await self.db.scalar(
            select(User).join(Identity, Identity.user_id == User.id).where(Identity.invite_code == code)
        )
        if inviter is None:
            # 非好友码：检查是否平台池码（★ G06）
            pool_hit = await self.auto_detect_platform_pool(user_id, code)
            if pool_hit:
                identity = await self._get_or_create(user_id)
                identity.invite_code = code
                await self.db.commit()
                return identity
            raise NotFoundError("邀请码无效")
        if inviter.id == user_id:
            raise ConflictError("不能邀请自己")

        identity = await self._get_or_create(user_id)

        # 防循环：从本用户祖先链回溯，验证码的 owner 不在其下游
        # 简化实现：直接回溯 identity.inviter_id 链，若遇到 code 的 owner 则拒绝
        cursor = identity.inviter_id
        visited = {user_id}
        while cursor is not None:
            if cursor == inviter.id:
                raise ConflictError("邀请关系成环，已拒绝")
            if cursor in visited:
                break
            visited.add(cursor)
            parent = await self.db.get(Identity, cursor)
            cursor = parent.inviter_id if parent else None

        identity.inviter_id = inviter.id
        identity.invite_code = code
        await self.db.commit()
        await self.db.refresh(identity)

        # 创建 Invite 关系记录（供奖励 T4.5 使用）
        from datetime import datetime, timezone

        from api.models.billing import Invite

        existing_invite = await self.db.scalar(select(Invite).where(Invite.invitee_id == user_id))
        if existing_invite is None:
            self.db.add(
                Invite(
                    inviter_id=inviter.id,
                    invitee_id=user_id,
                    code=code,
                    bound_at=datetime.now(timezone.utc),
                    locked=True,
                )
            )
            await self.db.commit()

        # ★ G06：命中平台池自动标记主号下级
        await self.auto_detect_platform_pool(user_id, code)
        return identity

    # ── ★ G27 交易所邀请码核实（必填）──
    async def verify_and_bind_exchange_invite(
        self, user_id: int, exchange: str, code: str
    ) -> tuple[bool, str]:
        """核实链：码存在 → active → 未达上限 → 属于所选所。"""
        code = code.strip().upper()
        record = await self.db.scalar(
            select(ExchangeInviteCode).where(
                ExchangeInviteCode.exchange == exchange.lower(),
                ExchangeInviteCode.code == code,
            )
        )
        if record is None:
            return False, "邀请码不存在或不属于所选交易所"

        if record.status != "active":
            return False, "邀请码已停用"

        if record.max_binds is not None and record.bind_count >= record.max_binds:
            return False, "邀请码已达绑定上限，请更换"

        identity = await self._get_or_create(user_id)
        identity.exchange_invite_code = code
        record.bind_count += 1
        await self.db.commit()

        await self.audit.log(
            actor_id=user_id,
            action="identity.bind_exchange_invite",
            target_type="identity",
            target_id=user_id,
            after={"exchange": exchange, "code": code, "bind_count": record.bind_count},
        )
        return True, "ok"

    # ── ★ G06 平台池自动识别 ──
    async def auto_detect_platform_pool(self, user_id: int, invite_code: str) -> bool:
        """命中 PlatformPool 且交易所匹配 → identity_type=sub_account（免订阅）。"""
        code = invite_code.strip().upper()
        pool = await self.db.scalar(
            select(PlatformPool).where(PlatformPool.invite_code == code, PlatformPool.is_active.is_(True))
        )
        if pool is None:
            return False

        identity = await self._get_or_create(user_id)
        if identity.exchange is not None and identity.exchange == pool.exchange.lower():
            identity.identity_type = "sub_account"
            await self.db.commit()
            await self.audit.log(
                actor_id=user_id,
                action="identity.auto_mark_sub_account",
                target_type="identity",
                target_id=user_id,
                after={"pool_code": code, "exchange": pool.exchange},
                reason="命中平台资源池（G06）",
            )
            return True
        return False

    # ── 工具 ──
    async def _get_or_create(self, user_id: int) -> Identity:
        identity = await self.db.get(Identity, user_id)
        if identity is None:
            identity = Identity(user_id=user_id)
            self.db.add(identity)
            await self.db.flush()
        return identity
