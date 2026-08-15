# 订阅到期/支付超时提醒（M4 完善 → 上线就绪：真实实现）
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from api.core.config import get_settings
from api.workers.celery_app import celery_app

logger = logging.getLogger("signal-saas.workers.reminder")

# 提醒窗口：到期前 24h / 72h 各推送一次（按日期去重）
WINDOWS_HOURS = (24, 72)
DEDUPE_TTL = 7 * 24 * 3600  # 去重键存活 7 天


@celery_app.task(name="reminder.subscription_expiring")
def remind_subscription_expiring() -> int:
    """订阅临期（24h/72h 窗口）推送站内消息 + 邮件，Redis 去重。"""
    try:
        asyncio.get_running_loop()
        raise RuntimeError("存在运行中的 loop，请 await remind_subscription_expiring_async()")
    except RuntimeError:
        return asyncio.run(remind_subscription_expiring_async())


async def remind_subscription_expiring_async() -> int:
    """async 核心：扫描 72h 内到期的 active 订阅，按用户聚合推送。"""
    from sqlalchemy import select

    from api.db.session import get_session_factory
    from api.models.billing import Subscription
    from api.models.user import User
    from api.services.mailer.service import Mailer
    from api.services.notification.service import NotificationService

    settings = get_settings()
    from redis import Redis

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=max(WINDOWS_HOURS))

    factory = get_session_factory()
    async with factory() as db:
        # 72h 窗口内 active 订阅（含 24h 内）
        rows = (
            await db.execute(
                select(Subscription).where(
                    Subscription.status == "active",
                    Subscription.expires_at <= window_end,
                    Subscription.expires_at > now,
                )
            )
        ).scalars().all()
        if not rows:
            return 0

        # 按用户聚合最近到期项
        by_user: dict[int, Subscription] = {}
        for sub in rows:
            cur = by_user.get(sub.user_id)
            if cur is None or sub.expires_at > cur.expires_at:
                by_user[sub.user_id] = sub

        sent = 0
        notifier = NotificationService(db)
        mailer = Mailer()
        for user_id, sub in by_user.items():
            expires_at = sub.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            remaining_h = (expires_at - now).total_seconds() / 3600
            window = 24 if remaining_h <= 24 else 72
            dedupe_key = f"reminder:expiring:{user_id}:{expires_at.date().isoformat()}:{window}h"
            if not redis.set(dedupe_key, "1", ex=DEDUPE_TTL, nx=True):
                continue  # 该用户该窗口已提醒过

            user = await db.get(User, user_id)
            if user is None:
                continue
            await notifier.push(
                user_id,
                type="subscription",
                title=f"订阅将于 {window} 小时内到期",
                body=f"到期时间 {expires_at.strftime('%Y-%m-%d %H:%M')} UTC；到期后暂停开仓/加仓，续费后恢复。",
            )
            try:
                await mailer.send_subscription_expiring(
                    user.email,
                    user.email.split("@")[0],
                    expires_at.strftime("%Y-%m-%d %H:%M UTC"),
                )
            except Exception as exc:  # noqa: BLE001 邮件失败不阻断站内消息
                logger.warning("expiring mail to %s failed: %s", user.email, exc)
            sent += 1
        await db.commit()
        return sent
