"""Общая логика работы с устройствами: настройки, выдача учёток, привязка."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Optional

import asyncpg

from .config import settings
from .mqtt import mqtt_admin
from .schemas import DeviceOut, ProvisionOut
from .security import generate_claim_code, generate_mqtt_password, hash_claim_code

log = logging.getLogger("binsense.devices")

# Поля настроек, которые хранятся в device_config.config и уезжают на устройство
CONFIG_FIELDS = (
    "interval_s",
    "heartbeat_s",
    "full_interval_s",
    "full_pct",
    "delta_pct",
    "samples",
)
# Поля калибровки — живут в таблице devices, но тоже уходят в настройках
CALIBRATION_FIELDS = ("empty_mm", "full_mm")


def default_config() -> dict[str, Any]:
    return {
        "interval_s": settings.default_interval_s,
        "heartbeat_s": settings.default_heartbeat_s,
        "full_interval_s": settings.default_full_interval_s,
        "full_pct": settings.default_full_pct,
        "delta_pct": settings.default_delta_pct,
        "samples": settings.default_samples,
    }


def build_config_payload(device: asyncpg.Record | dict, version: int, config: dict) -> dict:
    """Собирает JSON, который публикуется в retained-топик bins/<id>/config."""
    merged = {**default_config(), **(config or {})}
    return {
        "ver": version,
        "claimed": (device["status"] == "active"),
        "interval_s": merged["interval_s"],
        "heartbeat_s": merged["heartbeat_s"],
        "full_interval_s": merged["full_interval_s"],
        "full_pct": merged["full_pct"],
        "delta_pct": merged["delta_pct"],
        "samples": merged["samples"],
        "empty_mm": device["empty_mm"] or 0,
        "full_mm": device["full_mm"] or settings.default_full_mm,
    }


async def fetch_device(conn: asyncpg.Connection | asyncpg.Pool, device_id: str):
    return await conn.fetchrow(
        """
        SELECT d.*, c.version AS config_version, c.config AS config,
               c.applied_version AS config_applied_version,
               u.name AS owner_name, u.email AS owner_email,
               (SELECT count(*) FROM events e
                 WHERE e.device_id = d.id AND e.acked_at IS NULL AND e.needs_ack) AS open_events
          FROM devices d
          LEFT JOIN device_config c ON c.device_id = d.id
          LEFT JOIN users u ON u.id = d.owner_id
         WHERE d.id = $1
        """,
        device_id,
    )


def device_to_out(row: asyncpg.Record | dict) -> DeviceOut:
    config = {**default_config(), **(row.get("config") or {})}
    empty_mm = row["empty_mm"]
    return DeviceOut(
        id=row["id"],
        name=row["name"],
        address=row["address"],
        lat=row["lat"],
        lon=row["lon"],
        status=row["status"],
        online=row["online"],
        fill=row["last_fill"],
        dist_mm=row["last_dist_mm"],
        rssi=row["last_rssi"],
        last_seen=row["last_seen"],
        last_ts=row["last_ts"],
        empty_mm=empty_mm,
        full_mm=row["full_mm"],
        calibrated=bool(empty_mm),
        fw=row["fw"],
        hw=row["hw"],
        owner_id=row["owner_id"],
        owner_name=row.get("owner_name"),
        full_pct=config["full_pct"],
        config_version=row["config_version"],
        config_applied_version=row["config_applied_version"],
        config=config,
        open_events=row["open_events"] or 0,
        claimed_at=row["claimed_at"],
        created_at=row["created_at"],
    )


async def publish_config(pool: asyncpg.Pool, device_id: str) -> dict:
    """Читает актуальные настройки из БД и публикует их устройству."""
    row = await fetch_device(pool, device_id)
    if row is None:
        raise KeyError(device_id)
    payload = build_config_payload(row, row["config_version"] or 1, row["config"] or {})
    await mqtt_admin.publish_config(device_id, payload)
    return payload


async def bump_config(
    pool: asyncpg.Pool, device_id: str, changes: Optional[dict[str, Any]] = None
) -> dict:
    """Увеличивает версию настроек, сохраняет изменения и публикует их устройству."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT version, config FROM device_config WHERE device_id = $1 FOR UPDATE",
                device_id,
            )
            config = {**default_config(), **((row["config"] if row else None) or {})}
            if changes:
                config.update({k: v for k, v in changes.items() if k in CONFIG_FIELDS})
            version = (row["version"] if row else 0) + 1
            await conn.execute(
                """
                INSERT INTO device_config(device_id, version, config, updated_at)
                VALUES ($1, $2, $3, now())
                ON CONFLICT (device_id)
                DO UPDATE SET version = $2, config = $3, updated_at = now()
                """,
                device_id,
                version,
                config,
            )
    return await publish_config(pool, device_id)


async def provision_device(
    pool: asyncpg.Pool,
    device_id: str,
    hw: Optional[str] = None,
    fw: Optional[str] = None,
    reset_claim_code: bool = False,
) -> ProvisionOut:
    """«Заводская» подготовка: учётка MQTT, код привязки, запись в БД.

    Вызывается скриптом tools/provision.py перед выдачей устройства монтажнику.
    """
    device_id = device_id.strip().lower()
    password = generate_mqtt_password()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT * FROM devices WHERE id = $1", device_id)
        claim_code = generate_claim_code()
        if existing is None or reset_claim_code:
            code_hash = hash_claim_code(device_id, claim_code)
        else:
            code_hash = existing["claim_code_hash"]
            claim_code = ""  # код выдан при первой подготовке, второй раз не показываем

        if existing is None:
            await conn.execute(
                """
                INSERT INTO devices(id, claim_code_hash, hw, fw, full_mm, provisioned_at)
                VALUES ($1, $2, $3, $4, $5, now())
                """,
                device_id,
                code_hash,
                hw,
                fw,
                settings.default_full_mm,
            )
            await conn.execute(
                "INSERT INTO device_config(device_id, version, config) VALUES ($1, 1, $2)",
                device_id,
                default_config(),
            )
        else:
            await conn.execute(
                """
                UPDATE devices
                   SET claim_code_hash = $2,
                       hw = COALESCE($3, hw),
                       fw = COALESCE($4, fw),
                       claim_attempts = 0,
                       claim_locked_until = NULL,
                       provisioned_at = now()
                 WHERE id = $1
                """,
                device_id,
                code_hash,
                hw,
                fw,
            )

    await mqtt_admin.provision_device(device_id, password)
    await publish_config(pool, device_id)

    return ProvisionOut(
        device_id=device_id,
        mqtt_username=device_id,
        mqtt_password=password,
        mqtt_host=settings.device_mqtt_host,
        mqtt_port=settings.mqtt_public_port,
        claim_code=claim_code,
        claim_url=f"{settings.public_url.rstrip('/')}/claim?id={device_id}&code={claim_code}",
        created=existing is None,
    )


async def log_action(
    conn: asyncpg.Connection | asyncpg.Pool,
    user_id: Optional[int],
    action: str,
    device_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip: Optional[str] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO audit_log(user_id, action, device_id, details, ip)
        VALUES ($1, $2, $3, $4, $5)
        """,
        user_id,
        action,
        device_id,
        details or {},
        ip,
    )


def is_stale(last_seen: Optional[dt.datetime], heartbeat_s: int) -> bool:
    if last_seen is None:
        return True
    limit = dt.timedelta(seconds=heartbeat_s * settings.offline_factor)
    return dt.datetime.now(dt.timezone.utc) - last_seen > limit
