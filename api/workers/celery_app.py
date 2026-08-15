# Celery 应用（M2/M4 完善）
from __future__ import annotations

from celery import Celery

from api.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "signal_saas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "api.workers.tasks_signal",
        "api.workers.tasks_profile",
        "api.workers.tasks_payment",
        "api.workers.tasks_reward",
        "api.workers.tasks_reminder",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    beat_schedule={
        # ★ M2 T2.7：每日画像同步 凌晨 00:00-05:00（UTC 00:00 = 北京 08:00；按需求窗口调整）
        "profile-sync-daily": {
            "task": "profile.sync_daily",
            "schedule": 6 * 60 * 60,  # 每 6 小时（00/06/12/18 UTC）
            "options": {"expires": 60 * 30},
        },
        # ★ M2 T2.1：公开带单广场采集（每 30 分钟）
        "signal-scrape-all": {
            "task": "signal.scrape_all",
            "schedule": 30 * 60,
            "options": {"expires": 60 * 10},
        },
        # ★ 实时信号轮询（任务内按 signal_poll_interval 连续轮询，beat 每 loop_seconds 重踢一次）
        "signal-poll-live": {
            "task": "signal.poll_live",
            "schedule": settings.signal_poll_loop_seconds,
            "options": {"expires": max(settings.signal_poll_loop_seconds - 5, 5)},
        },
        # ★ 全量对账（每 signal_reconcile_interval 秒强制重同步基线，兜底漂移）
        "signal-reconcile": {
            "task": "signal.reconcile",
            "schedule": settings.signal_reconcile_interval,
            "options": {"expires": max(settings.signal_reconcile_interval - 5, 5)},
        },
        # ★ M4 T4.4：支付轮询（每 2 分钟扫 pending 轮询态）
        "payment-poll": {
            "task": "payment.poll_sweep",
            "schedule": 2 * 60,
        },
        # ★ M4 T4.5：奖励核实释放（每 10 分钟）
        "reward-scan": {
            "task": "reward.scan_verifying",
            "schedule": 10 * 60,
        },
    },
)
