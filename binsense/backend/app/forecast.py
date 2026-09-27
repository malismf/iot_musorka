"""Прогноз заполнения контейнера — линейная регрессия по последним измерениям."""
from __future__ import annotations

import datetime as dt
from typing import Optional, Sequence


def linear_fit(points: Sequence[tuple[dt.datetime, float]]) -> Optional[tuple[float, float]]:
    """Возвращает (наклон в %/час, свободный член) по методу наименьших квадратов."""
    if len(points) < 3:
        return None
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 3600.0 for t, _ in points]
    ys = [float(v) for _, v in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom <= 1e-9:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    return slope, mean_y - slope * mean_x


def forecast_fill(
    points: Sequence[tuple[dt.datetime, float]],
    current_fill: Optional[int],
    full_pct: int,
) -> dict:
    """Оценка, когда контейнер достигнет порога заполнения."""
    result: dict = {
        "rate_pct_per_day": None,
        "hours_to_full": None,
        "eta": None,
        "points_used": len(points),
        "note": "",
    }
    if current_fill is None:
        result["note"] = "устройство не откалибровано"
        return result
    if current_fill >= full_pct:
        result["hours_to_full"] = 0.0
        result["eta"] = dt.datetime.now(dt.timezone.utc)
        result["note"] = "контейнер уже заполнен"
        return result

    fit = linear_fit(points)
    if fit is None:
        result["note"] = "мало данных для прогноза"
        return result

    slope, _ = fit
    result["rate_pct_per_day"] = round(slope * 24, 1)
    if slope <= 0.01:
        result["note"] = "заполнение не растёт"
        return result

    hours = (full_pct - current_fill) / slope
    hours = max(0.0, min(hours, 24 * 60))  # больше двух месяцев не прогнозируем
    result["hours_to_full"] = round(hours, 1)
    result["eta"] = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)
    return result
