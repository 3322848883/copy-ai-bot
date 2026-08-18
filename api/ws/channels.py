# 10 个 WS 频道定义（设计 §7.2）
from __future__ import annotations

CHANNELS: tuple[str, ...] = (
    "strategy.update",      # 策略画像更新
    "signal.new",           # 新信号（命中用户 bot 时推送）
    "bot.position",         # 仓位变化
    "bot.order",            # 下单结果
    "pnl.tick",             # 盈亏实时
    "account.balance",      # 余额实时
    "reward.tick",          # 奖励状态（含 24h 倒计时）
    "withdrawal.status",    # 提现状态
    "notification.new",     # 站内消息实时推送
    "announcement.new",     # 平台公告广播
)
