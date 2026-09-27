"""Пул соединений с PostgreSQL и применение миграций."""
from __future__ import annotations

import json
import logging
import pathlib

import asyncpg

from .config import settings

log = logging.getLogger("binsense.db")

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"
# Блокировка, чтобы мигрировала только одна реплика (api / ingestor / bot стартуют вместе)
MIGRATION_LOCK_ID = 0x1B155E01


async def _init_connection(conn: asyncpg.Connection) -> None:
    # asyncpg по умолчанию отдаёт jsonb строкой — включаем автоматический json
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        dsn or settings.database_url,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        init=_init_connection,
        command_timeout=30,
    )
    assert pool is not None
    return pool


async def migrate(pool: asyncpg.Pool) -> list[str]:
    """Применяет .sql файлы из migrations/ по порядку. Возвращает список применённых."""
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_ID)
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version    TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            done = {
                r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")
            }
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in done:
                    continue
                log.info("применяю миграцию %s", path.name)
                async with conn.transaction():
                    await conn.execute(path.read_text(encoding="utf-8"))
                    await conn.execute(
                        "INSERT INTO schema_migrations(version) VALUES ($1)", path.name
                    )
                applied.append(path.name)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_ID)
    return applied


async def notify(conn_or_pool, channel: str, payload: dict) -> None:
    """Рассылка события внутри кластера через LISTEN/NOTIFY (для WebSocket)."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text.encode()) > 7000:  # лимит полезной нагрузки NOTIFY ~8000 байт
        text = json.dumps({"type": payload.get("type"), "truncated": True}, ensure_ascii=False)
    await conn_or_pool.execute("SELECT pg_notify($1, $2)", channel, text)
