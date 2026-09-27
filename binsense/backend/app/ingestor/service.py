"""Ingestor: приём MQTT-сообщений, запись в БД, правила и события."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from typing import Any, Optional

import aiomqtt
import asyncpg
import pydantic

from ..config import settings
from ..devices import build_config_payload, default_config, device_to_out, fetch_device
from ..events import broadcast, store_event
from ..mqtt import mqtt_admin
from ..rules import (
    device_event,
    evaluate_telemetry,
    evaluate_urgent,
    offline_event,
    online_event,
)
from ..schemas import DeviceEventIn, TelemetryIn

log = logging.getLogger("binsense.ingestor")

MIN_PLAUSIBLE_TS = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)


def _utc(seconds: Optional[int]) -> Optional[dt.datetime]:
    if not seconds:
        return None
    try:
        value = dt.datetime.fromtimestamp(int(seconds), tz=dt.timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None
    if value < MIN_PLAUSIBLE_TS:
        return None
    if value > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10):
        return None
    return value


class Ingestor:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # --- телеметрия ----------------------------------------------------------
    async def handle_telemetry(self, device_id: str, raw: bytes) -> bool:
        try:
            data = TelemetryIn.model_validate_json(raw)
        except pydantic.ValidationError as exc:
            log.warning("некорректная телеметрия от %s: %s", device_id, exc.errors()[:2])
            return False

        device = await fetch_device(self.pool, device_id)
        if device is None:
            log.warning("телеметрия от неизвестного устройства %s", device_id)
            return False

        now = dt.datetime.now(dt.timezone.utc)
        ts = _utc(data.ts) or now
        config = {**default_config(), **(device["config"] or {})}

        inserted = await self.pool.fetchrow(
            """
            INSERT INTO telemetry(device_id, ts, received_at, seq, boot_id, fill,
                                  dist_mm, rssi, wake)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            device_id,
            ts,
            now,
            data.seq,
            data.boot,
            data.fill,
            data.dist_mm,
            data.rssi,
            data.wake,
        )
        if inserted is None:
            log.info("дубль телеметрии %s seq=%s — пропускаю", device_id, data.seq)
            return False

        state: dict[str, Any] = dict(device["state"] or {})
        lost = 0
        if data.seq is not None and data.boot is not None:
            if state.get("last_boot") == data.boot and state.get("last_seq") is not None:
                lost = max(0, int(data.seq) - int(state["last_seq"]) - 1)
            state["last_seq"] = int(data.seq)
            state["last_boot"] = int(data.boot)

        await self.pool.execute(
            """
            INSERT INTO device_metrics(device_id, ts, seq, boot_id, latency_ms, wake_ms,
                                       wifi_ms, mqtt_ms, rssi, lost, wake, reset_reason)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            device_id,
            now,
            data.seq,
            data.boot,
            int((now - ts).total_seconds() * 1000),
            data.wake_ms,
            data.wifi_ms,
            data.mqtt_ms,
            data.rssi,
            lost,
            data.wake,
            data.reset,
        )

        merged: dict[str, Any] = dict(device)
        merged.update(
            {
                "last_fill": data.fill if data.fill is not None else device["last_fill"],
                "last_dist_mm": data.dist_mm,
                "last_rssi": data.rssi,
                "last_seen": now,
                "last_ts": ts,
                "fw": data.fw or device["fw"],
                "hw": data.hw or device["hw"],
                "online": True,
            }
        )

        specs = []
        if not device["online"] and device["status"] == "active" and device["last_seen"]:
            specs.append(online_event(merged))
        rule_events, state = evaluate_telemetry(
            merged, state, data.fill, int(config["full_pct"])
        )
        specs.extend(rule_events)

        await self.pool.execute(
            """
            UPDATE devices
               SET last_seen = $2, last_ts = $3, last_fill = COALESCE($4, last_fill),
                   last_dist_mm = $5, last_rssi = $6,
                   fw = COALESCE($7, fw), hw = COALESCE($8, hw),
                   online = TRUE, state = $9
             WHERE id = $1
            """,
            device_id,
            now,
            ts,
            data.fill,
            data.dist_mm,
            data.rssi,
            data.fw,
            data.hw,
            state,
        )
        merged["state"] = state

        # устройство подтвердило применение настроек
        if data.cfg_ver is not None and data.cfg_ver != (device["config_applied_version"] or 0):
            await self.pool.execute(
                """UPDATE device_config SET applied_version = $2, applied_at = now()
                    WHERE device_id = $1""",
                device_id,
                data.cfg_ver,
            )
            merged["config_applied_version"] = data.cfg_ver

        await broadcast(
            self.pool,
            {"type": "telemetry", "device": device_to_out(merged).model_dump(mode="json")},
        )
        for spec in specs:
            await store_event(self.pool, merged, spec)
        return True

    # --- события устройства --------------------------------------------------
    async def handle_event(self, device_id: str, raw: bytes) -> bool:
        try:
            payload = DeviceEventIn.model_validate_json(raw)
        except pydantic.ValidationError as exc:
            log.warning("некорректное событие от %s: %s", device_id, exc.errors()[:2])
            return False

        device = await fetch_device(self.pool, device_id)
        if device is None:
            log.warning("событие от неизвестного устройства %s", device_id)
            return False

        merged = dict(device)
        # калибровка: сохраняем глубину и синхронизируем настройки
        if payload.type == "calibrated" and payload.empty_mm:
            await self.pool.execute(
                "UPDATE devices SET empty_mm = $2, full_mm = COALESCE($3, full_mm) WHERE id = $1",
                device_id,
                payload.empty_mm,
                payload.full_mm,
            )
            merged["empty_mm"] = payload.empty_mm
            if payload.full_mm:
                merged["full_mm"] = payload.full_mm
            await self._republish_config(merged)

        if payload.type == "hello":
            await self.pool.execute(
                """UPDATE devices
                      SET fw = COALESCE($2, fw), hw = COALESCE($3, hw),
                          last_seen = now(), online = TRUE
                    WHERE id = $1""",
                device_id,
                payload.fw,
                payload.hw,
            )
            merged["fw"] = payload.fw or device["fw"]
            # координаты от GPS, если место ещё не задано
            if payload.lat and payload.lon and device["lat"] is None:
                await self.pool.execute(
                    "UPDATE devices SET lat = $2, lon = $3 WHERE id = $1",
                    device_id,
                    payload.lat,
                    payload.lon,
                )
                merged["lat"], merged["lon"] = payload.lat, payload.lon

        spec = device_event(merged, payload)
        if spec is not None:
            await store_event(self.pool, merged, spec)
        await broadcast(
            self.pool,
            {"type": "telemetry", "device": device_to_out(merged).model_dump(mode="json")},
        )
        return True

    async def _republish_config(self, device) -> None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE device_config SET version = version + 1, updated_at = now()
                    WHERE device_id = $1 RETURNING version, config""",
                device["id"],
            )
        if row is None:
            return
        payload = build_config_payload(device, row["version"], row["config"] or {})
        try:
            await mqtt_admin.publish_config(device["id"], payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("не удалось опубликовать настройки %s: %s", device["id"], exc)

    # --- периодические проверки ---------------------------------------------
    async def check_offline(self) -> int:
        rows = await self.pool.fetch(
            """
            SELECT d.*, c.version AS config_version, c.config AS config,
                   c.applied_version AS config_applied_version,
                   NULL::text AS owner_name, 0::bigint AS open_events,
                   COALESCE((c.config ->> 'heartbeat_s')::int, $1) AS heartbeat_s
              FROM devices d
              LEFT JOIN device_config c ON c.device_id = d.id
             WHERE d.status = 'active' AND d.online
               AND (d.last_seen IS NULL
                    OR d.last_seen < now() - make_interval(
                         secs => COALESCE((c.config ->> 'heartbeat_s')::int, $1) * $2))
            """,
            settings.default_heartbeat_s,
            settings.offline_factor,
        )
        for row in rows:
            await self.pool.execute("UPDATE devices SET online = FALSE WHERE id = $1", row["id"])
            merged = dict(row)
            merged["online"] = False
            await store_event(self.pool, merged, offline_event(merged, row["heartbeat_s"]))
            await broadcast(
                self.pool,
                {"type": "telemetry", "device": device_to_out(merged).model_dump(mode="json")},
            )
        return len(rows)

    async def check_urgent(self) -> int:
        rows = await self.pool.fetch(
            """
            SELECT d.*, c.version AS config_version, c.config AS config,
                   c.applied_version AS config_applied_version,
                   NULL::text AS owner_name, 0::bigint AS open_events,
                   (SELECT max(acked_at) FROM events e
                     WHERE e.device_id = d.id AND e.type = 'full'
                       AND e.created_at > now() - interval '2 days') AS full_ack_at
              FROM devices d
              LEFT JOIN device_config c ON c.device_id = d.id
             WHERE d.status = 'active'
               AND (d.state ->> 'full_active') = 'true'
               AND COALESCE((d.state ->> 'urgent_sent')::bool, FALSE) = FALSE
               AND d.last_fill >= $1
            """,
            settings.urgent_fill,
        )
        count = 0
        for row in rows:
            specs, state = evaluate_urgent(row, dict(row["state"] or {}), row["full_ack_at"])
            if not specs:
                continue
            await self.pool.execute(
                "UPDATE devices SET state = $2 WHERE id = $1", row["id"], state
            )
            for spec in specs:
                await store_event(self.pool, row, spec)
            count += 1
        return count

    async def cleanup(self) -> None:
        await self.pool.execute(
            "DELETE FROM telemetry WHERE received_at < now() - make_interval(days => $1)",
            settings.telemetry_retention_days,
        )
        await self.pool.execute(
            "DELETE FROM device_metrics WHERE ts < now() - make_interval(days => $1)",
            settings.metrics_retention_days,
        )
        await self.pool.execute(
            "DELETE FROM api_requests WHERE ts < now() - make_interval(days => $1)",
            settings.metrics_retention_days,
        )

    # --- циклы ---------------------------------------------------------------
    async def periodic_loop(self, interval: float = 60.0) -> None:
        last_cleanup = dt.datetime.now(dt.timezone.utc)
        while True:
            try:
                await self.check_offline()
                await self.check_urgent()
                if dt.datetime.now(dt.timezone.utc) - last_cleanup > dt.timedelta(hours=24):
                    await self.cleanup()
                    last_cleanup = dt.datetime.now(dt.timezone.utc)
            except Exception as exc:  # noqa: BLE001
                log.exception("ошибка периодической проверки: %s", exc)
            await asyncio.sleep(interval)

    async def dispatch(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != settings.mqtt_topic_prefix:
            return
        _, device_id, kind = parts
        try:
            if kind == "telemetry":
                await self.handle_telemetry(device_id, payload)
            elif kind == "event":
                await self.handle_event(device_id, payload)
        except Exception as exc:  # noqa: BLE001
            log.exception("ошибка обработки %s: %s", topic, exc)

    async def mqtt_loop(self) -> None:
        prefix = settings.mqtt_topic_prefix
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_host,
                    port=settings.mqtt_port,
                    username=settings.mqtt_admin_user,
                    password=settings.mqtt_admin_password,
                    identifier="binsense-ingestor",
                    clean_session=False,  # брокер копит сообщения, пока ingestor перезапускается
                    keepalive=60,
                ) as client:
                    await client.subscribe(f"{prefix}/+/telemetry", qos=1)
                    await client.subscribe(f"{prefix}/+/event", qos=1)
                    log.info("подписка на %s/+/telemetry и /event", prefix)
                    async for message in client.messages:
                        await self.dispatch(str(message.topic), bytes(message.payload or b""))
            except aiomqtt.MqttError as exc:
                log.warning("MQTT недоступен (%s), переподключение через 5 с", exc)
                await asyncio.sleep(5)

    async def run(self) -> None:
        await asyncio.gather(self.mqtt_loop(), self.periodic_loop())


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
