# Celery 应用（M2/M4 完善）
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

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
        # ★ 生产核查修复：copy.process_signal 任务定义于此，必须随 worker 注册
        "api.workers.consumer_signal",
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
            # ★ 修复：0-5 点每小时一次（原 6h×4 次与"每日画像"语义不符）
            "schedule": crontab(hour="0-5", minute="0"),
            "options": {"expires": 60 * 30},
        },
        # ★ M2 T2.1：公开带单广场采集（每 30 分钟）
        "signal-scrape-all": {
            "task": "signal.scrape_all",
            "schedule": 30 * 60,
            "options": {"expires": 60 * 10},
        },
        # ★ 需求补充：信号源详情(画像)定时刷新——所有已上架策略画像按日 upsert，保证策略广场数据新鲜
        "signal-refresh-listed-profiles": {
            "task": "signal.refresh_listed_profiles",
            "schedule": settings.signal_profile_refresh_interval,
            "options": {"expires": max(settings.signal_profile_refresh_interval, 60)},
        },
        # ★ 实时信号轮询（任务内按 signal_poll_interval 连续轮询，beat 每 loop_seconds 重踢一次）
        "signal-poll-live": {
            "task": "signal.poll_live",
            "schedule": settings.signal_poll_loop_seconds,
            # ★ 修复：expires 放宽至 2 倍，防任务慢跑导致消息队列过期形成轮询空窗
            "options": {"expires": max(settings.signal_poll_loop_seconds * 2, 60)},
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
        # ★ H4：TTL 过期清理（每 2 分钟，pending 超 30min → expired）
        "payment-expire": {
            "task": "payment.expire_sweep",
            "schedule": 2 * 60,
        },
        # ★ M4 T4.5：奖励核实释放（每 10 分钟）
        "reward-scan": {
            "task": "reward.scan_verifying",
            "schedule": 10 * 60,
        },
        # ★ 订阅临期提醒（每小时扫描 72h/24h 窗口）
        "reminder-subscription-expiring": {
            "task": "reminder.subscription_expiring",
            "schedule": 3600.0,
        },
    },
)
