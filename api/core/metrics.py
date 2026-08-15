"""Prometheus 指标工厂（M6 T6.2：6 核心指标落地，替换占位实现）。"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── HTTP ──
http_requests_total = Counter(
    "http_requests_total", "HTTP 请求总数", ["method", "path", "status"]
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP 请求耗时（秒）", ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")),
)

# ── WebSocket ──
ws_connections_active = Gauge("ws_connections_active", "当前 WS 在线连接数")

# ── 业务（计划 §7.3 六指标）──
# 1. signal_received_total{exchange,source}
signal_received_total = Counter(
    "signal_received_total", "收到信号总数", ["exchange", "source"]
)
# 2. risk_decisions_total{decision}
risk_decisions_total = Counter(
    "risk_decisions_total", "风控决策总数", ["decision"]
)
# 3. orders_placed_total{exchange,result}（派生 gauge：/metrics 抓取时 set 全量值，避免 Counter 累加膨胀）
app_copy_orders_filled_total = Gauge("app_copy_orders_filled_total", "跟单成功订单数（当前值）")
app_copy_orders_failed_total = Gauge("app_copy_orders_failed_total", "跟单失败订单数（当前值）")
# 4. payment_poll_attempts_total{network}
payment_poll_attempts_total = Counter(
    "payment_poll_attempts_total", "支付轮询次数", ["network"]
)
# 5. withdrawal_pending_total
withdrawal_pending_total = Gauge("withdrawal_pending_total", "待处理提现数")
# 6. http_request_duration_seconds（Histogram，见上）

# ── 补充派生指标 ──
app_users_total = Gauge("app_users_total", "注册用户数")
app_payments_confirmed_total = Gauge("app_payments_confirmed_total", "已确认支付订单数（当前值）")
app_audit_events_total = Gauge("app_audit_events_total", "审计事件数")


def trace_span(name: str):
    """上下文管理器占位（接 OpenTelemetry 扩展点）。"""

    class _Span:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return _Span()
