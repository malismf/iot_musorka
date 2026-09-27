#!/usr/bin/env bash
# Резервная копия базы данных и учётных записей брокера.
#
#   ./infra/scripts/backup.sh [каталог]
#
# Для ежедневного бэкапа добавьте в crontab:
#   0 3 * * * cd /opt/binsense && ./infra/scripts/backup.sh >> /var/log/binsense-backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/../.."
TARGET="${1:-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M)"
mkdir -p "$TARGET"

echo "== База данных"
docker compose exec -T db pg_dump -U binsense binsense | gzip -9 > "$TARGET/db-$STAMP.sql.gz"

echo "== Учётные записи брокера"
docker compose exec -T mqtt cat /mosquitto/data/dynamic-security.json \
    > "$TARGET/dynamic-security-$STAMP.json"

echo "== Настройки"
cp .env "$TARGET/env-$STAMP" 2>/dev/null || true
chmod 600 "$TARGET"/* 2>/dev/null || true

echo "== Удаляю копии старше $KEEP_DAYS дней"
find "$TARGET" -type f -mtime "+$KEEP_DAYS" -print -delete

echo "Готово: $TARGET"
ls -lh "$TARGET" | tail -5
