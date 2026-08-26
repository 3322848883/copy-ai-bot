"""交易所订单对账：修复响应丢失或进程中断造成的本地状态不一致。"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from api.core.config import get_settings
from api.exchange_clients.registry import get_adapter
from api.models.bot import CopyBot, CopyOrder
from api.models.signal import SourceSignal
from api.models.user import ApiKey
from api.services.apikeyvault.service import ApiKeyVaultService
from api.services.copyengine.service import CopyEngine
from api.services.executor.service import ExecResult
from api.workers.celery_app import celery_app

logger = logging.getLogger("signal-saas.order-reconcile")


@celery_app.task(name="order.reconcile_uncertain")
def reconcile_uncertain_orders() -> str:
    return asyncio.run(_reconcile_uncertain_orders())


async def _reconcile_uncertain_orders() -> str:
    from api.db.session import get_engine, get_session_factory

    factory = get_session_factory()
    checked = repaired = 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        async with factory() as db:
            rows = (
                await db.execute(
                    select(CopyOrder)
                    .join(CopyBot, CopyBot.id == CopyOrder.bot_id)
                    .where(
                        CopyBot.paper.is_(False),
                        CopyOrder.client_order_id.is_not(None),
                        CopyOrder.status.in_(("pending", "failed")),
                        CopyOrder.created_at >= cutoff,
                    )
                    .order_by(CopyOrder.id.asc())
                    .limit(200)
                )
            ).scalars().all()
            engine = CopyEngine(db)
            for order in rows:
                checked += 1
                try:
                    bot = await db.get(CopyBot, order.bot_id)
                    sig = await db.get(SourceSignal, order.signal_id)
                    api_row = await db.get(ApiKey, bot.api_key_id) if bot else None
                    if not bot or not sig or not api_row or api_row.status != "active":
                        continue
                    plain = ApiKeyVaultService(get_settings().vault_key_hex).decrypt(
                        api_row.ciphertext, api_row.nonce, api_row.tag, api_row.aad
                    )
                    api_key, _, api_secret = plain.partition("\n")
                    adapter = get_adapter(bot.exchange)
                    lookup_id = order.exchange_order_id or order.client_order_id
                    result = await adapter.fetch_order(lookup_id, api_key, api_secret)
                    if result is None:
                        continue
                    if result.status == "filled" and result.filled_qty > 0:
                        order.status = "filled"
                        order.filled_qty = result.filled_qty
                        order.avg_price = result.avg_price if result.avg_price > 0 else None
                        order.exchange_order_id = result.order_id or order.exchange_order_id
                        order.failure_category = None
                        order.fail_reason = None
                        order.executed_at = datetime.now(timezone.utc)
                        if order.action in ("open", "add"):
                            bot.virtual_locked_usdt += order.required_margin_usdt
                        await engine._sync_position(
                            bot,
                            sig,
                            ExecResult(
                                True,
                                order_id=result.order_id,
                                filled_qty=result.filled_qty,
                                avg_price=result.avg_price,
                            ),
                        )
                        await db.commit()
                        await CopyEngine._push_order_update(bot, sig, order)
                        repaired += 1
                    elif result.status == "cancelled" and order.status == "pending":
                        order.status = "failed"
                        order.failure_category = "other"
                        order.fail_reason = "交易所对账确认：订单未成交并已撤销"
                        order.exchange_order_id = result.order_id or order.exchange_order_id
                        await db.commit()
                        await CopyEngine._push_order_update(bot, sig, order)
                        repaired += 1
                except Exception:  # noqa: BLE001 单笔失败不影响其他用户订单
                    await db.rollback()
                    logger.exception("order reconcile failed: copy_order=%s", order.id)
    finally:
        await get_engine().dispose()
    return f"checked={checked}, repaired={repaired}"
