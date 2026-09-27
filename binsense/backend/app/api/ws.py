"""WebSocket: живые обновления карты.

Ingestor и API работают в разных контейнерах, поэтому события передаются
через PostgreSQL LISTEN/NOTIFY — отдельный брокер (Redis) не нужен.
"""
from __future__ import annotations

import asyncio
import json
import logging

import asyncpg
from fastapi import WebSocket

from ..events import WS_CHANNEL

log = logging.getLogger("binsense.ws")


class WebSocketHub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self._conn: asyncpg.Connection | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self, pool: asyncpg.Pool) -> None:
        self._loop = asyncio.get_running_loop()
        self._conn = await pool.acquire()
        await self._conn.add_listener(WS_CHANNEL, self._on_notify)
        log.info("слушаю канал %s", WS_CHANNEL)

    async def stop(self, pool: asyncpg.Pool) -> None:
        if self._conn is not None:
            try:
                await self._conn.remove_listener(WS_CHANNEL, self._on_notify)
                await pool.release(self._conn)
            except Exception:  # noqa: BLE001  # pragma: no cover
                pass
            self._conn = None

    def _on_notify(self, _conn, _pid, _channel, payload: str) -> None:
        if self._loop is None:
            return
        self._loop.create_task(self.broadcast(payload))

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)
        await websocket.send_text(json.dumps({"type": "hello"}))

    def disconnect(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def broadcast(self, payload: str) -> None:
        dead = []
        for client in list(self.clients):
            try:
                await client.send_text(payload)
            except Exception:  # noqa: BLE001 — клиент отвалился
                dead.append(client)
        for client in dead:
            self.clients.discard(client)


hub = WebSocketHub()
