#!/usr/bin/env bash
# signal-saas PostgreSQL 每日全量备份（M6 T6.6）
# 用法: POSTGRES_PASSWORD=xxx PGDATABASE=signal_saas ./scripts/backup_pg.sh
# cron 示例: 0 3 * * * cd /opt/signal-saas && POSTGRES_PASSWORD=xxx ./scripts/backup_pg.sh >> /var/log/signal-saas-backup.log 2>&1
set -euo pipefail

PGUSER="${PGUSER:-signal}"
PGDATABASE="${PGDATABASE:-signal_saas}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${KEEP:-14}"

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F-%H%M%S)"
DUMP="${BACKUP_DIR}/${PGDATABASE}_${STAMP}.dump"

echo "[backup] dumping ${PGDATABASE} -> ${DUMP}"
pg_dump -U "$PGUSER" -h "$PGHOST" -p "$PGPORT" -Fc "$PGDATABASE" > "$DUMP"
echo "[backup] done: $(du -h "$DUMP" | cut -f1)"

# 轮转：仅保留最近 KEEP 份
ls -1t "${BACKUP_DIR}/${PGDATABASE}_"*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "[backup] keep last ${KEEP}; oldest removed"
