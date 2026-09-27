"""Устройства: список, карточка, привязка, настройки, история."""
from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from ...config import settings
from ...devices import (
    CALIBRATION_FIELDS,
    CONFIG_FIELDS,
    bump_config,
    default_config,
    device_to_out,
    fetch_device,
    log_action,
)
from ...events import broadcast, store_event
from ...rules import EventSpec
from ...schemas import (
    ClaimIn,
    DeviceOut,
    DeviceUpdateIn,
    EventOut,
    TelemetryPoint,
)
from ...security import verify_claim_code
from ..deps import EditorDep, PoolDep, UserDep, client_ip

router = APIRouter(prefix="/devices", tags=["devices"])

MAX_CLAIM_ATTEMPTS = 10
CLAIM_LOCK_MINUTES = 15

LIST_QUERY = """
    SELECT d.*, c.version AS config_version, c.config AS config,
           c.applied_version AS config_applied_version,
           u.name AS owner_name,
           (SELECT count(*) FROM events e
             WHERE e.device_id = d.id AND e.acked_at IS NULL AND e.needs_ack) AS open_events
      FROM devices d
      LEFT JOIN device_config c ON c.device_id = d.id
      LEFT JOIN users u ON u.id = d.owner_id
"""


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    pool: PoolDep,
    user: UserDep,
    mine: bool = False,
    include_unclaimed: bool = False,
) -> list[DeviceOut]:
    where = [] if include_unclaimed else ["d.status = 'active'"]
    params: list = []
    if mine:
        params.append(user["id"])
        where.append(f"d.owner_id = ${len(params)}")
    sql = LIST_QUERY + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY d.name NULLS LAST, d.id"
    rows = await pool.fetch(sql, *params)
    return [device_to_out(row) for row in rows]


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: str, pool: PoolDep, user: UserDep) -> DeviceOut:
    row = await fetch_device(pool, device_id.lower())
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Устройство не найдено")
    return device_to_out(row)


@router.post("/claim", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def claim_device(body: ClaimIn, pool: PoolDep, user: EditorDep, request: Request) -> DeviceOut:
    """Привязка устройства к аккаунту по коду привязки (его выдаёт tools/provision.py)."""
    row = await pool.fetchrow("SELECT * FROM devices WHERE id = $1", body.device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Устройство не найдено")
    if row["claim_locked_until"] and row["claim_locked_until"] > dt.datetime.now(dt.timezone.utc):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Слишком много попыток, попробуйте позже",
        )
    if row["status"] == "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Устройство уже привязано")

    if not verify_claim_code(body.device_id, body.claim_code, row["claim_code_hash"]):
        attempts = row["claim_attempts"] + 1
        locked = (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=CLAIM_LOCK_MINUTES)
            if attempts >= MAX_CLAIM_ATTEMPTS
            else None
        )
        await pool.execute(
            "UPDATE devices SET claim_attempts = $2, claim_locked_until = $3 WHERE id = $1",
            body.device_id,
            attempts,
            locked,
        )
        await log_action(
            pool, user["id"], "claim_failed", body.device_id, {"attempts": attempts},
            ip=client_ip(request),
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный код привязки")

    await pool.execute(
        """
        UPDATE devices
           SET owner_id = $2, status = 'active', name = $3, address = $4,
               lat = $5, lon = $6,
               claim_attempts = 0, claim_locked_until = NULL, claimed_at = now()
         WHERE id = $1
        """,
        body.device_id,
        user["id"],
        body.name,
        body.address,
        body.lat,
        body.lon,
    )
    await bump_config(pool, body.device_id)  # публикует claimed = true
    await log_action(pool, user["id"], "claim", body.device_id, ip=client_ip(request))

    device = await fetch_device(pool, body.device_id)
    await store_event(
        pool,
        device,
        EventSpec(
            type="claimed",
            message=f"Устройство привязано: {body.name} ({user['email']})",
            data={"user_id": user["id"]},
        ),
    )
    out = device_to_out(device)
    await broadcast(pool, {"type": "telemetry", "device": out.model_dump(mode="json")})
    return out


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: str,
    body: DeviceUpdateIn,
    pool: PoolDep,
    user: EditorDep,
    request: Request,
) -> DeviceOut:
    device_id = device_id.lower()
    row = await fetch_device(pool, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Устройство не найдено")

    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    card_fields = {
        k: v for k, v in patch.items()
        if k in ("name", "address", "lat", "lon")
    }
    # Новая версия настроек — только если значение для устройства действительно
    # изменилось: форма присылает все поля сразу, а карточка (название, место)
    # хранится лишь на сервере
    current = {**default_config(), **(row["config"] or {})}
    calibration = {
        k: v for k, v in patch.items() if k in CALIBRATION_FIELDS and row[k] != v
    }
    config_changes = {
        k: v for k, v in patch.items() if k in CONFIG_FIELDS and current.get(k) != v
    }

    if card_fields or calibration:
        updates = {**card_fields, **calibration}
        assignments = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
        await pool.execute(
            f"UPDATE devices SET {assignments} WHERE id = $1", device_id, *updates.values()
        )

    if config_changes or calibration:
        await bump_config(pool, device_id, config_changes)

    await log_action(pool, user["id"], "update_device", device_id, patch, ip=client_ip(request))
    device = await fetch_device(pool, device_id)
    out = device_to_out(device)
    await broadcast(pool, {"type": "telemetry", "device": out.model_dump(mode="json")})
    return out


@router.delete("/{device_id}/claim", response_model=DeviceOut)
async def unclaim_device(
    device_id: str, pool: PoolDep, user: EditorDep, request: Request
) -> DeviceOut:
    """Отвязать устройство (например, чтобы перенести на другой контейнер)."""
    device_id = device_id.lower()
    row = await fetch_device(pool, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Устройство не найдено")
    if user["role"] != "admin" and row["owner_id"] != user["id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Отвязать может владелец или администратор")

    await pool.execute(
        """
        UPDATE devices
           SET status = 'unclaimed', owner_id = NULL, online = FALSE,
               claimed_at = NULL, state = '{}'::jsonb
         WHERE id = $1
        """,
        device_id,
    )
    await bump_config(pool, device_id)  # claimed = false
    await log_action(pool, user["id"], "unclaim", device_id, ip=client_ip(request))
    device = await fetch_device(pool, device_id)
    await store_event(
        pool,
        device,
        EventSpec(type="unclaimed", message=f"Устройство отвязано: {device_id}"),
    )
    out = device_to_out(device)
    await broadcast(pool, {"type": "telemetry", "device": out.model_dump(mode="json")})
    return out


@router.get("/{device_id}/telemetry", response_model=list[TelemetryPoint])
async def device_telemetry(
    device_id: str,
    pool: PoolDep,
    user: UserDep,
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24,
    bucket: Literal["raw", "5m", "1h", "1d"] = "raw",
    limit: Annotated[int, Query(ge=1, le=5000)] = 2000,
) -> list[TelemetryPoint]:
    device_id = device_id.lower()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    if bucket == "raw":
        rows = await pool.fetch(
            """
            SELECT ts, fill, dist_mm, rssi
              FROM telemetry
             WHERE device_id = $1 AND ts >= $2
             ORDER BY ts
             LIMIT $3
            """,
            device_id,
            since,
            limit,
        )
        return [
            TelemetryPoint(
                ts=r["ts"],
                fill=r["fill"],
                fill_max=r["fill"],
                dist_mm=r["dist_mm"],
                rssi=r["rssi"],
            )
            for r in rows
        ]

    step = {"5m": "5 minutes", "1h": "1 hour", "1d": "1 day"}[bucket]
    rows = await pool.fetch(
        f"""
        SELECT date_bin(interval '{step}', ts, timestamptz '2024-01-01') AS bin,
               avg(fill)::float AS fill,
               max(fill)::float AS fill_max,
               avg(dist_mm)::float AS dist_mm,
               avg(rssi)::float AS rssi
          FROM telemetry
         WHERE device_id = $1 AND ts >= $2
         GROUP BY bin
         ORDER BY bin
         LIMIT $3
        """,
        device_id,
        since,
        limit,
    )
    return [
        TelemetryPoint(
            ts=r["bin"],
            fill=round(r["fill"], 1) if r["fill"] is not None else None,
            fill_max=r["fill_max"],
            dist_mm=r["dist_mm"],
            rssi=round(r["rssi"], 1) if r["rssi"] is not None else None,
        )
        for r in rows
    ]


@router.get("/{device_id}/events", response_model=list[EventOut])
async def device_events(
    device_id: str,
    pool: PoolDep,
    user: UserDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[EventOut]:
    rows = await pool.fetch(
        """
        SELECT e.*, d.name AS device_name, u.name AS acked_by_name
          FROM events e
          LEFT JOIN devices d ON d.id = e.device_id
          LEFT JOIN users u ON u.id = e.acked_by
         WHERE e.device_id = $1
         ORDER BY e.created_at DESC
         LIMIT $2
        """,
        device_id.lower(),
        limit,
    )
    return [EventOut(**dict(r)) for r in rows]
