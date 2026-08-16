#!/usr/bin/env bash
# signal-saas 备份恢复演练（M6 T6.7 清单 §5）
# 将最新备份恢复到"全新空库"，防止误覆盖生产库（默认限制到 localhost:5433 新实例）。
# 用法:
#   POSTGRES_PASSWORD=xxx PGDATABASE=signal_saas ./scripts/restore_pg.sh [backup_file]
#   （不传 backup_file 时取 backups/ 下最新一份）
set -euo pipefail

PGUSER="${PGUSER:-signal}"
PGDATABASE="${PGDATABASE:-signal_saas}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5433}"          # 恢复目标端口，默认 5433（演练专用新实例）
BACKUP_DIR="${BACKUP_DIR:-./backups}"

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"

if [ "$PGPORT" = "5432" ]; then
  echo "[restore] 警告：目标端口为 5432（生产库），请确认！Enter 继续，Ctrl-C 中止。"
  read -r _
fi

DUMP="${1:-$(ls -1t "${BACKUP_DIR}/${PGDATABASE}_"*.dump 2>/dev/null | head -n 1)}"
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "[restore] 未找到备份文件：$DUMP"
  exit 1
fi

echo "[restore] 恢复到 ${PGHOST}:${PGPORT}/${PGDATABASE} <- $DUMP"
# --clean 先清空再重建目标 schema；--if-exists 容错
pg_restore -U "$PGUSER" -h "$PGHOST" -p "$PGPORT" -d "$PGDATABASE" --clean --if-exists --no-owner --no-privileges "$DUMP"
echo "[restore] 完成"

echo "[restore] 冒烟检查：用户数 / 订单数 / 订阅数"
psql -U "$PGUSER" -h "$PGHOST" -p "$PGPORT" -d "$PGDATABASE" -tAc \
  "select (select count(*) from users) as users, (select count(*) from payment_orders) as orders, (select count(*) from subscriptions) as subs;"