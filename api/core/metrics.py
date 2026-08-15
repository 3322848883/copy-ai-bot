"""Prometheus 指标工厂。"""
from __future__ import annotations

from typing import Callable

# 占位：M0 T0.8 接入 prometheus_client
Metric = Callable

_metrics: dict[str, object] = {}


def metrics_counter(name: str, labels: dict[str, str] | None = None) -> object:
    """获取/创建 Counter（占位实现，M6 接 prometheus_client）。"""
    if name not in _metrics:
        _metrics[name] = {"type": "counter", "labels": labels or {}}
    return _metrics[name]


def trace_span(name: str):
    """上下文管理器占位。"""

    class _Span:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return _Span()
