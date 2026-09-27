"""Запуск ingestor: python -m app.ingestor"""
from __future__ import annotations

import asyncio
import logging
import sys

from ..config import settings
from ..db import create_pool, migrate
from ..mqtt import mqtt_admin
from .service import Ingestor

log = logging.getLogger("binsense.ingestor")


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    pool = await create_pool()
    await migrate(pool)
    try:
        await mqtt_admin.ensure_backend_role()
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось настроить роль backend в брокере: %s", exc)

    ingestor = Ingestor(pool)
    log.info("ingestor запущен, брокер %s:%s", settings.mqtt_host, settings.mqtt_port)
    try:
        await ingestor.run()
    finally:
        await pool.close()


if __name__ == "__main__":
    # aiomqtt работает только с SelectorEventLoop, а на Windows по умолчанию Proactor
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        asyncio.run(main(), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass
