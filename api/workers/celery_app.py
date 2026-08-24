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
        "api.workers.tasks_paper",
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
        #   ★ 相位修复（2026-08-20）：原 timedelta 1800s 相位随 beat 启动时刻漂移，
        #     实测漂到 11/41 分与 refresh(17/47) 只差 6 分钟、与 reconcile(600s 公倍数点)
        #     每 30 分钟必然同秒触发——三者互抢 data/scraper-bulk 的 ProcessSingleton 锁。
        #     改 crontab 固定 :02/:32，与 refresh(:17/:47) 错开 15 分钟、
        #     与 reconcile(:09 起) 错开 7 分钟，批量任务各占独立窗口。
        "signal-scrape-all": {
            "task": "signal.scrape_all",
            "schedule": crontab(minute="2,32"),
            "options": {"expires": 60 * 10},
        },
        # ★ 需求补充：信号源详情(画像)定时刷新——所有已上架策略画像按日 upsert，保证策略广场数据新鲜
        #   ★ 错峰修复：原 1800s 固定间隔与 scrape_all（同为 1800s）从 beat 启动同刻起算，
        #     每 30 分钟同时触发争抢 data/scraper 浏览器目录（SingletonLock 冲突实锤）。
        #     改为每小时 17/47 分（间隔 30 分钟），与整点采集错开 ≥17 分钟。
        "signal-refresh-listed-profiles": {
            "task": "signal.refresh_listed_profiles",
            "schedule": crontab(minute="17,47"),
            "options": {"expires": max(settings.signal_profile_refresh_interval, 60)},
        },
        # ★ 实时信号轮询（任务内按 signal_poll_interval 连续轮询，beat 定时重踢）
        #   ★ 调度间隔 = 循环时长 + 15s 余量：任务总耗时 = loop + 浏览器启停开销(~5-10s)，
        #     若间隔 == loop，相邻两轮任务永久重叠，互抢 data/scraper 的
        #     ProcessSingleton 锁（实测每轮损失 ~30 轮询）；留余量后干净交接。
        "signal-poll-live": {
            "task": "signal.poll_live",
            # ★ 余量 15→10s（2026-08-20）：实测浏览器启停开销 ~1s，10s 足够；
            #   任务循环时长 110s（config signal_poll_loop_seconds），空窗 10s/120s ≈ 8%
            "schedule": settings.signal_poll_loop_seconds + 10,
            # ★ 修复：expires 放宽至 2 倍，防任务慢跑导致消息队列过期形成轮询空窗
            "options": {"expires": max(settings.signal_poll_loop_seconds * 2, 60)},
        },
        # ★ 全量对账（强制重同步基线，兜底漂移）
        #   ★ 相位修复（2026-08-20）：原 timedelta（默认 600s）相位随 beat 启动漂移，
        #     与 scrape_all(1800s) 的公倍数点每 30 分钟同秒触发互抢 bulk 浏览器。
        #     改 crontab 每 10 分钟（:09 起），避开 scrape(:02/:32) 与 refresh(:17/:47)。
        #   ★ 调整对账频率请改此 minute 列表（signal_reconcile_interval 不再驱动调度）。
        "signal-reconcile": {
            "task": "signal.reconcile",
            "schedule": crontab(minute="9,19,29,39,49,59"),
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
        # ★ P1 对账：confirmed 但订阅未激活/奖励未触发的订单补偿（每 5 分钟）
        "payment-confirm-reconcile": {
            "task": "payment.confirm_reconcile",
            "schedule": 5 * 60,
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
        # ★ 数据保留期清理（每日凌晨 03:00 UTC = 北京 11:00）：
        #   删除超期的 source_signals（默认 90 天）和已关闭的老 position_snapshots（默认 30 天），
        #   防止信号表/快照表无限增长拖慢查询性能。
        "signal-vacuum-retention": {
            "task": "signal.vacuum_retention",
            "schedule": crontab(hour="3", minute="0"),
        },
        # ★ 模拟盘 mark_price REST 兜底刷新（每 60s）：WS 实时通道断线时保证价格新鲜。
        #   与 api 容器内 gate_ticker WS 任务互为保险，双通道任一存活即可刷新盈亏。
        "paper-update-marks": {
            "task": "paper.update_marks",
            "schedule": 60.0,
            "options": {"expires": 50},
        },
    },
)
