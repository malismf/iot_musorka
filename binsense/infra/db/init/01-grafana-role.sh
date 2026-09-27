#!/bin/bash
# Выполняется один раз при создании базы: заводит роль только для чтения,
# под которой Grafana ходит за метриками. Пароли пользователей ей не видны
# (см. REVOKE в миграции backend/migrations/001_init.sql).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE grafana_ro LOGIN PASSWORD '${GRAFANA_DB_PASSWORD:-grafana}';
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO grafana_ro;
    GRANT USAGE ON SCHEMA public TO grafana_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
        GRANT SELECT ON TABLES TO grafana_ro;
EOSQL
