#!/usr/bin/env python3
"""Собирает дашборд Grafana из описания панелей.

Писать большой JSON руками неудобно и легко ошибиться, поэтому панели описаны
здесь, а файл dashboards/binsense.json генерируется командой:

    python infra/grafana/make_dashboard.py

Дашборд отвечает за пункт 12 задания: доступность устройств, потери сообщений,
задержки доставки, качество связи, время ответа API.
"""
from __future__ import annotations

import json
import pathlib

DATASOURCE = {"type": "grafana-postgresql-datasource", "uid": "binsense-pg"}
OUT = pathlib.Path(__file__).resolve().parent / "dashboards" / "binsense.json"

panels: list[dict] = []
_next_id = 1
_cursor = {"x": 0, "y": 0, "row_height": 0}


def _place(width: int, height: int) -> dict:
    """Простейшая раскладка: заполняем строку шириной 24 и переходим ниже."""
    if _cursor["x"] + width > 24:
        _cursor["x"] = 0
        _cursor["y"] += _cursor["row_height"]
        _cursor["row_height"] = 0
    position = {"h": height, "w": width, "x": _cursor["x"], "y": _cursor["y"]}
    _cursor["x"] += width
    _cursor["row_height"] = max(_cursor["row_height"], height)
    return position


def panel(kind: str, title: str, sql: str, width: int = 12, height: int = 8,
          fmt: str = "time_series", unit: str | None = None, description: str = "",
          options: dict | None = None) -> None:
    global _next_id
    item = {
        "id": _next_id,
        "type": kind,
        "title": title,
        "description": description,
        "datasource": DATASOURCE,
        "gridPos": _place(width, height),
        "targets": [
            {
                "refId": "A",
                "datasource": DATASOURCE,
                "format": fmt,
                "rawQuery": True,
                "rawSql": sql.strip(),
            }
        ],
        "fieldConfig": {"defaults": {"custom": {}}, "overrides": []},
        "options": options or {},
    }
    if unit:
        item["fieldConfig"]["defaults"]["unit"] = unit
    if kind == "stat":
        item["options"] = options or {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "auto",
            "textMode": "auto",
            "colorMode": "value",
            "graphMode": "area",
        }
    panels.append(item)
    _next_id += 1


# --- Верхний ряд: состояние парка устройств ----------------------------------
panel(
    "stat", "Устройств на связи",
    """
    SELECT count(*) FILTER (WHERE online) AS "на связи"
      FROM devices WHERE status = 'active'
    """,
    width=4, height=5, fmt="table",
)
panel(
    "stat", "Устройств всего",
    """
    SELECT count(*) AS "всего" FROM devices WHERE status = 'active'
    """,
    width=4, height=5, fmt="table",
)
panel(
    "stat", "Доступность, %",
    """
    SELECT round(100.0 * count(*) FILTER (WHERE online) / NULLIF(count(*), 0), 1)
             AS "доступность"
      FROM devices WHERE status = 'active'
    """,
    width=4, height=5, fmt="table", unit="percent",
)
panel(
    "stat", "Сообщений за период",
    """
    SELECT count(*) AS "сообщений"
      FROM telemetry WHERE $__timeFilter(received_at)
    """,
    width=4, height=5, fmt="table",
)
panel(
    "stat", "Потеряно сообщений, %",
    """
    SELECT round(100.0 * COALESCE(sum(lost), 0) /
                 NULLIF(count(*) + COALESCE(sum(lost), 0), 0), 2) AS "потери"
      FROM device_metrics WHERE $__timeFilter(ts)
    """,
    width=4, height=5, fmt="table", unit="percent",
    description="Считается по разрывам счётчика seq в телеметрии",
)
panel(
    "stat", "Ошибок API (5xx)",
    """
    SELECT count(*) AS "5xx" FROM api_requests
     WHERE status >= 500 AND $__timeFilter(ts)
    """,
    width=4, height=5, fmt="table",
)

# --- Качество связи -----------------------------------------------------------
panel(
    "timeseries", "Задержка доставки телеметрии",
    """
    SELECT $__timeGroupAlias(ts, $__interval),
           percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS "медиана",
           percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS "95-й процентиль"
      FROM device_metrics
     WHERE $__timeFilter(ts) AND latency_ms IS NOT NULL
     GROUP BY 1
     ORDER BY 1
    """,
    unit="ms",
    description="Разница между временем измерения на устройстве и временем приёма сервером",
)
panel(
    "timeseries", "Время подключения устройства",
    """
    SELECT $__timeGroupAlias(ts, $__interval),
           avg(wifi_ms) AS "подключение Wi-Fi",
           avg(mqtt_ms) AS "подключение MQTT"
      FROM device_metrics
     WHERE $__timeFilter(ts)
     GROUP BY 1
     ORDER BY 1
    """,
    unit="ms",
    description="Сколько заняло последнее подключение к Wi-Fi и брокеру: растёт — связь ухудшается",
)
panel(
    "timeseries", "Уровень сигнала Wi-Fi",
    """
    SELECT $__timeGroupAlias(ts, $__interval),
           COALESCE(d.name, m.device_id) AS metric,
           avg(m.rssi) AS "rssi"
      FROM device_metrics m
      LEFT JOIN devices d ON d.id = m.device_id
     WHERE $__timeFilter(m.ts) AND m.rssi IS NOT NULL
     GROUP BY 1, 2
     ORDER BY 1
    """,
    unit="dBm",
)
# --- Сервер -------------------------------------------------------------------
panel(
    "timeseries", "Время ответа API",
    """
    SELECT $__timeGroupAlias(ts, $__interval),
           percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) AS "медиана",
           percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS "95-й процентиль"
      FROM api_requests
     WHERE $__timeFilter(ts)
     GROUP BY 1
     ORDER BY 1
    """,
    unit="ms",
)
panel(
    "timeseries", "Запросы к API по кодам ответа",
    """
    SELECT $__timeGroupAlias(ts, $__interval),
           status::text AS metric,
           count(*) AS "запросов"
      FROM api_requests
     WHERE $__timeFilter(ts)
     GROUP BY 1, 2
     ORDER BY 1
    """,
)

# --- Таблицы ------------------------------------------------------------------
panel(
    "table", "Простой устройств (нет связи)",
    """
    SELECT COALESCE(d.name, e.device_id) AS "контейнер",
           count(*) AS "случаев",
           round(sum(EXTRACT(EPOCH FROM (COALESCE(e.resolved_at, now()) - e.created_at)))
                 / 3600.0, 1) AS "часов без связи"
      FROM events e
      JOIN devices d ON d.id = e.device_id
     WHERE e.type = 'offline' AND $__timeFilter(e.created_at)
     GROUP BY 1
     ORDER BY 3 DESC
     LIMIT 20
    """,
    fmt="table",
)
panel(
    "table", "Причины перезагрузок",
    """
    SELECT reset_reason AS "причина", count(*) AS "раз"
      FROM device_metrics
     WHERE reset_reason IS NOT NULL AND $__timeFilter(ts)
     GROUP BY 1
     ORDER BY 2 DESC
    """,
    fmt="table",
)
panel(
    "table", "Последние сбои датчиков",
    """
    SELECT e.created_at AS "время",
           COALESCE(d.name, e.device_id) AS "контейнер",
           e.message AS "сообщение"
      FROM events e
      LEFT JOIN devices d ON d.id = e.device_id
     WHERE e.type = 'sensor_error' AND $__timeFilter(e.created_at)
     ORDER BY e.created_at DESC
     LIMIT 50
    """,
    fmt="table",
)
panel(
    "table", "Устройства: прошивка и настройки",
    """
    SELECT d.id AS "устройство", d.name AS "название", d.fw AS "прошивка",
           c.version AS "версия настроек", c.applied_version AS "применено",
           d.last_seen AS "последние данные"
      FROM devices d
      LEFT JOIN device_config c ON c.device_id = d.id
     WHERE d.status = 'active'
     ORDER BY d.last_seen DESC NULLS LAST
    """,
    fmt="table",
    width=24,
)

dashboard = {
    "uid": "binsense-tech",
    "title": "BinSense — техническое состояние",
    "description": "Мониторинг уровня разработчика: доступность, потери, задержки, связь",
    "tags": ["binsense"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "1m",
    "time": {"from": "now-24h", "to": "now"},
    "editable": True,
    "panels": panels,
}

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(f"готово: {OUT} ({len(panels)} панелей)")
