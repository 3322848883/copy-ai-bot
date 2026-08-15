"""结构化日志 + trace_id。"""
from __future__ import annotations

import logging
import sys
import uuid


def setup_logging(service: str, level: str = "INFO") -> None:
    """初始化结构化日志（M0 T0.8）。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    ))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("signal_saas").info("logging ready for %s", service)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]
