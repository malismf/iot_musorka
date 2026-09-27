"""Лента событий и подтверждение («Принято»)."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from ...devices import log_action
from ...events import broadcast
from ...schemas import EventOut
from ..deps import PoolDep, UserDep, client_ip

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventOut])
async def list_events(
    pool: PoolDep,
    user: UserDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    only_open: bool = False,
    severity: Optional[str] = None,
    device_id: Optional[str] = None,
) -> list[EventOut]:
    where = ["TRUE"]
    params: list = []
    if only_open:
        where.append("e.needs_ack AND e.acked_at IS NULL")
    if severity:
        params.append(severity)
        where.append(f"e.severity = ${len(params)}")
    if device_id:
        params.append(device_id.lower())
        where.append(f"e.device_id = ${len(params)}")
    params.append(limit)
    rows = await pool.fetch(
        f"""
        SELECT e.*, d.name AS device_name, u.name AS acked_by_name
          FROM events e
          LEFT JOIN devices d ON d.id = e.device_id
          LEFT JOIN users u ON u.id = e.acked_by
         WHERE {' AND '.join(where)}
         ORDER BY e.created_at DESC
         LIMIT ${len(params)}
        """,
        *params,
    )
    return [EventOut(**dict(r)) for r in rows]


@router.post("/{event_id}/ack", response_model=EventOut)
async def ack_event(event_id: int, pool: PoolDep, user: UserDep, request: Request) -> EventOut:
    row = await pool.fetchrow(
        """
        UPDATE events
           SET acked_by = $2, acked_at = COALESCE(acked_at, now())
         WHERE id = $1
        RETURNING *
        """,
        event_id,
        user["id"],
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Событие не найдено")
    await log_action(
        pool, user["id"], "ack_event", row["device_id"], {"event_id": event_id},
        ip=client_ip(request),
    )
    await broadcast(
        pool,
        {"type": "event_ack", "event_id": event_id, "acked_by": user["name"] or user["email"]},
    )
    full = await pool.fetchrow(
        """
        SELECT e.*, d.name AS device_name, u.name AS acked_by_name
          FROM events e
          LEFT JOIN devices d ON d.id = e.device_id
          LEFT JOIN users u ON u.id = e.acked_by
         WHERE e.id = $1
        """,
        event_id,
    )
    return EventOut(**dict(full))
