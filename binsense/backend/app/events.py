"""Запись событий в базу, рассылка в Telegram и в WebSocket."""
from __future__ import annotations

import logging
from typing import Optional

from .db import notify as pg_notify
from .notify import TelegramClient, notify_event
from .rules import AUDIENCE, EventSpec

log = logging.getLogger("binsense.events")

WS_CHANNEL = "binsense_ws"


async def broadcast(pool, payload: dict) -> None:
    """Сообщение для всех подключённых WebSocket-клиентов (через LISTEN/NOTIFY)."""
    try:
        await pg_notify(pool, WS_CHANNEL, payload)
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось разослать событие в WebSocket: %s", exc)


async def store_event(
    pool,
    device,
    spec: EventSpec,
    telegram: Optional[TelegramClient] = None,
) -> int:
    device_id = device["id"] if device is not None else None
    async with pool.acquire() as conn:
        async with conn.transaction():
            if spec.resolves and device_id:
                await conn.execute(
                    """
                    UPDATE events
                       SET resolved_at = now()
                     WHERE device_id = $1 AND type = ANY($2::text[]) AND resolved_at IS NULL
                    """,
                    device_id,
                    list(spec.resolves),
                )
            row = await conn.fetchrow(
                """
                INSERT INTO events(device_id, type, severity, message, data, needs_ack)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, created_at
                """,
                device_id,
                spec.type,
                spec.severity,
                spec.message,
                spec.data,
                spec.needs_ack,
            )
    event_id = row["id"]

    await broadcast(
        pool,
        {
            "type": "event",
            "event": {
                "id": event_id,
                "device_id": device_id,
                "device_name": device["name"] if device is not None else None,
                "type": spec.type,
                "severity": spec.severity,
                "message": spec.message,
                "data": spec.data,
                "needs_ack": spec.needs_ack,
                "created_at": row["created_at"].isoformat(),
            },
        },
    )

    if telegram is not None:
        try:
            await notify_event(
                pool,
                telegram,
                event_id,
                spec.type,
                spec.severity,
                spec.message,
                spec.data,
                device,
                AUDIENCE.get(spec.type, ()),
                spec.needs_ack,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("ошибка рассылки уведомлений по событию %s: %s", event_id, exc)

    log.info("событие %s (%s) устройства %s", spec.type, spec.severity, device_id)
    return event_id
