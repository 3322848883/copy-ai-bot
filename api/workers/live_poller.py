"""生产实时信号常驻进程：避免短周期 Celery 任务交接造成采集空窗。"""
from __future__ import annotations

import asyncio
import logging

from api.workers.tasks_signal import _poll_live_loop

logger = logging.getLogger("signal-saas.live-poller")


async def main() -> None:
    # _poll_live_loop 内部隔离单轮故障；只有初始化级异常才会退避后重建会话。
    while True:
        try:
            await _poll_live_loop(continuous=True)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("live poller crashed; restarting in 5 seconds")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
