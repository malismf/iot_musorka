#!/usr/bin/env bash
# Восстановление из резервной копии, созданной backup.sh.
#
#   ./infra/scripts/restore.sh backups/db-20261201-0300.sql.gz
#
# Внимание: текущие данные в базе будут заменены.
set -euo pipefail

cd "$(dirname "$0")/../.."
DUMP="${1:?укажите файл дампа, например backups/db-20261201-0300.sql.gz}"

read -r -p "Восстановить $DUMP поверх текущей базы? (yes/нет) " answer
[ "$answer" = "yes" ] || { echo "отменено"; exit 1; }

echo "== Останавливаю сервисы, которые пишут в базу"
docker compose stop api ingestor

echo "== Пересоздаю базу"
docker compose exec -T db psql -U binsense -d postgres -c "DROP DATABASE IF EXISTS binsense;"
docker compose exec -T db psql -U binsense -d postgres -c "CREATE DATABASE binsense OWNER binsense;"

echo "== Заливаю дамп"
gunzip -c "$DUMP" | docker compose exec -T db psql -U binsense -d binsense

echo "== Запускаю сервисы"
docker compose start api ingestor
echo "Готово"
