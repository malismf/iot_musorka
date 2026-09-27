"""Правила, по которым телеметрия превращается в события.

Функции этого модуля — чистые: на вход состояние устройства и новые значения,
на выход список событий и новое состояние. Это позволяет покрыть правила тестами
без базы и без брокера (см. tests/test_rules.py).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import settings

@dataclass
class EventSpec:
    type: str
    message: str
    severity: str = "info"
    needs_ack: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    resolves: tuple[str, ...] = ()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def device_title(device) -> str:
    name = device["name"] or device["id"]
    address = device["address"]
    return f"{name} — {address}" if address else str(name)


def evaluate_telemetry(
    device,
    state: dict[str, Any],
    fill: Optional[int],
    full_pct: int,
) -> tuple[list[EventSpec], dict[str, Any]]:
    """Основные правила: заполнение и вывоз."""
    events: list[EventSpec] = []
    state = dict(state or {})
    title = device_title(device)

    if fill is not None:
        max_fill = max(int(state.get("max_fill") or 0), fill)
        state["max_fill"] = max_fill

        if fill >= full_pct and not state.get("full_active"):
            state["full_active"] = True
            state["full_since"] = _now().isoformat()
            state["urgent_sent"] = False
            events.append(
                EventSpec(
                    type="full",
                    severity="warning",
                    needs_ack=True,
                    message=f"Контейнер заполнен на {fill}%: {title}",
                    data={"fill": fill, "full_pct": full_pct},
                )
            )

        collected = (
            max_fill >= settings.collected_high_pct
            and fill <= settings.collected_low_pct
        )
        if collected:
            events.append(
                EventSpec(
                    type="collected",
                    severity="info",
                    message=f"Контейнер вывезен: {title} (было {max_fill}%, стало {fill}%)",
                    data={"fill_before": max_fill, "fill_after": fill},
                    resolves=("full", "full_urgent"),
                )
            )
            state["full_active"] = False
            state["urgent_sent"] = False
            state["max_fill"] = fill
            state["last_collection"] = _now().isoformat()

    return events, state


def evaluate_urgent(device, state: dict[str, Any], full_ack_at) -> tuple[list[EventSpec], dict]:
    """Периодическая проверка: заполнен под завязку и никто не отреагировал."""
    state = dict(state or {})
    fill = device["last_fill"]
    if (
        not state.get("full_active")
        or state.get("urgent_sent")
        or fill is None
        or fill < settings.urgent_fill
        or full_ack_at is not None
    ):
        return [], state

    since = state.get("full_since")
    if not since:
        return [], state
    try:
        full_since = dt.datetime.fromisoformat(since)
    except ValueError:
        return [], state
    if _now() - full_since < dt.timedelta(minutes=settings.urgent_delay_min):
        return [], state

    state["urgent_sent"] = True
    hours = settings.urgent_delay_min // 60
    return [
        EventSpec(
            type="full_urgent",
            severity="critical",
            needs_ack=True,
            message=(
                f"Срочно вывезти: {device_title(device)} — {fill}%, "
                f"событие не подтверждено {hours} ч"
            ),
            data={"fill": fill},
        )
    ], state


def offline_event(device, heartbeat_s: int) -> EventSpec:
    last_seen = device["last_seen"]
    when = last_seen.strftime("%d.%m %H:%M") if last_seen else "никогда"
    return EventSpec(
        type="offline",
        severity="warning",
        needs_ack=True,
        message=f"Нет связи с устройством: {device_title(device)} (последние данные {when})",
        data={"heartbeat_s": heartbeat_s},
    )


def online_event(device) -> EventSpec:
    return EventSpec(
        type="online",
        severity="info",
        message=f"Устройство снова в сети: {device_title(device)}",
        resolves=("offline",),
    )


def device_event(device, payload) -> Optional[EventSpec]:
    """События, которые устройство присылает само (топик bins/<id>/event)."""
    title = device_title(device)
    kind = payload.type
    if kind == "calibrated":
        return EventSpec(
            type="calibrated",
            severity="info",
            message=f"Выполнена калибровка: {title}, глубина {(payload.empty_mm or 0) / 10:.0f} см",
            data={"empty_mm": payload.empty_mm, "full_mm": payload.full_mm},
        )
    if kind in ("error", "sensor_error"):
        return EventSpec(
            type="sensor_error",
            severity="warning",
            needs_ack=True,
            message=f"Сбой датчика ({payload.code or 'unknown'}): {title}",
            data={"code": payload.code},
        )
    if kind == "hello":
        return EventSpec(
            type="hello",
            severity="info",
            message=f"Устройство включено: {title} (fw {payload.fw or '?'}, {payload.reset or '?'})",
            data={"fw": payload.fw, "reset": payload.reset},
        )
    return EventSpec(
        type=kind[:40],
        severity="info",
        message=f"{title}: {payload.message or kind}",
        data=payload.data,
    )
