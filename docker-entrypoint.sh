#!/usr/bin/env bash
# 容器入口：按 SCRAPER_HEADLESS 决定是否挂 Xvfb 虚拟屏。
#   - 默认/SCRAPER_HEADLESS=true → 无头直接跑（无需显示）
#   - SCRAPER_HEADLESS=false      → 有头采集，用 Xvfb 虚拟屏承载（Akamai 更稳）
#
# ★ 2026-08 修复：不再用 xvfb-run（其 wait+SIGUSR1 就绪机制在容器 PID1 环境下
#   会卡死，导致业务命令永不执行）；改为显式后台启动 Xvfb + 导出 DISPLAY。
set -e

if [ "${SCRAPER_HEADLESS}" = "false" ] || [ "${SCRAPER_HEADLESS}" = "0" ]; then
  echo "[entrypoint] SCRAPER_HEADLESS=false → start Xvfb virtual display (1440x900x24)"
  Xvfb :99 -screen 0 1440x900x24 -nolisten tcp -nolisten unix &
  export DISPLAY=:99
  # 等待 Xvfb socket 就绪（最多 5s），随后 exec 业务命令（alembic/uvicorn/celery）
  for _ in $(seq 1 25); do
    if [ -e /tmp/.X11-unix/X99 ] || [ -e /tmp/.X99-lock ]; then
      break
    fi
    sleep 0.2
  done
  sleep 0.5
  # ★ 清理残留浏览器锁（容器重建后 user_data_dir 中可能残留 SingletonLock，
  #   指向已不存在的旧进程 socket，导致 signal_session 启动崩溃）
  if [ -n "${SIGNAL_SESSION_DATA_DIR:-}" ] && [ -d "${SIGNAL_SESSION_DATA_DIR}" ]; then
    rm -f "${SIGNAL_SESSION_DATA_DIR}"/Singleton* 2>/dev/null || true
    echo "[entrypoint] cleaned stale Singleton locks in ${SIGNAL_SESSION_DATA_DIR}"
  fi
  echo "[entrypoint] DISPLAY=${DISPLAY} ready → exec $*"
  exec "$@"
fi

echo "[entrypoint] headless mode (SCRAPER_HEADLESS=${SCRAPER_HEADLESS:-<auto>})"
exec "$@"
