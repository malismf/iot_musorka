"""Сводка по системе и планирование маршрута вывоза."""
from __future__ import annotations

import math
from typing import Annotated, Optional

from fastapi import APIRouter, Query

from ...config import settings
from ...schemas import RouteOut, RouteStop, StatsOut
from ..deps import PoolDep, UserDep

router = APIRouter(tags=["stats"])

EARTH_R_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


@router.get("/stats/overview", response_model=StatsOut)
async def overview(pool: PoolDep, user: UserDep) -> StatsOut:
    row = await pool.fetchrow(
        """
        SELECT
            count(*) AS devices,
            count(*) FILTER (WHERE status = 'active') AS active,
            count(*) FILTER (WHERE status = 'unclaimed') AS unclaimed,
            count(*) FILTER (WHERE status = 'active' AND online) AS online,
            count(*) FILTER (WHERE status = 'active' AND NOT online) AS offline,
            count(*) FILTER (WHERE status = 'active'
                             AND last_fill >= COALESCE((c.config ->> 'full_pct')::int, $1)
                            ) AS full,
            count(*) FILTER (WHERE status = 'active' AND (empty_mm IS NULL OR empty_mm = 0))
                AS uncalibrated,
            avg(last_fill) FILTER (WHERE status = 'active') AS avg_fill
          FROM devices d
          LEFT JOIN device_config c ON c.device_id = d.id
        """,
        settings.default_full_pct,
    )
    open_events = await pool.fetchval(
        "SELECT count(*) FROM events WHERE needs_ack AND acked_at IS NULL"
    )
    collected = await pool.fetchval(
        """SELECT count(*) FROM events
            WHERE type = 'collected' AND created_at > now() - interval '7 days'"""
    )
    return StatsOut(
        devices=row["devices"],
        active=row["active"],
        unclaimed=row["unclaimed"],
        online=row["online"],
        offline=row["offline"],
        full=row["full"],
        uncalibrated=row["uncalibrated"],
        avg_fill=round(float(row["avg_fill"]), 1) if row["avg_fill"] is not None else None,
        open_events=open_events or 0,
        collected_7d=collected or 0,
    )


@router.get("/route", response_model=RouteOut)
async def build_route(
    pool: PoolDep,
    user: UserDep,
    min_fill: Annotated[int, Query(ge=0, le=100)] = 80,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> RouteOut:
    """Простой маршрут «ближайший следующий» по заполненным контейнерам."""
    rows = await pool.fetch(
        """
        SELECT id, name, address, lat, lon, last_fill
          FROM devices
         WHERE status = 'active' AND lat IS NOT NULL AND lon IS NOT NULL
           AND last_fill >= $1
         ORDER BY last_fill DESC
        """,
        min_fill,
    )
    remaining = [dict(r) for r in rows]
    stops: list[RouteStop] = []
    total = 0.0
    cur_lat, cur_lon = (lat, lon) if lat is not None and lon is not None else (None, None)

    while remaining:
        if cur_lat is None:
            nxt = remaining.pop(0)
        else:
            nxt = min(remaining, key=lambda d: haversine(cur_lat, cur_lon, d["lat"], d["lon"]))
            total += haversine(cur_lat, cur_lon, nxt["lat"], nxt["lon"])
            remaining.remove(nxt)
        cur_lat, cur_lon = nxt["lat"], nxt["lon"]
        stops.append(
            RouteStop(
                device_id=nxt["id"],
                name=nxt["name"],
                address=nxt["address"],
                lat=nxt["lat"],
                lon=nxt["lon"],
                fill=nxt["last_fill"],
            )
        )

    return RouteOut(stops=stops, total_km=round(total, 2), map_urls=google_maps_urls(stops))


def google_maps_urls(stops: list[RouteStop], chunk: int = 10) -> list[str]:
    """Ссылки на Google Maps (до 9 промежуточных точек в одной ссылке)."""
    urls: list[str] = []
    for start in range(0, len(stops), chunk):
        part = stops[start : start + chunk]
        if not part:
            continue
        origin = f"{part[0].lat},{part[0].lon}"
        destination = f"{part[-1].lat},{part[-1].lon}"
        waypoints = "|".join(f"{s.lat},{s.lon}" for s in part[1:-1])
        url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={origin}&destination={destination}&travelmode=driving"
        )
        if waypoints:
            url += f"&waypoints={waypoints}"
        urls.append(url)
    return urls
