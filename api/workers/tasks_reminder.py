# 订阅到期/支付超时提醒（M4 完善）
from __future__ import annotations

from api.workers.celery_app import celery_app


@celery_app.task(name="reminder.subscription_expiring")
def remind_subscription_expiring() -> int:
    """订阅临期推送站内消息 + 邮件。"""
    raise NotImplementedError("M4 实现")
