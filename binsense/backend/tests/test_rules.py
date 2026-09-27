"""Тесты правил, прогноза и вспомогательных функций (без базы и брокера)."""
from __future__ import annotations

import datetime as dt

from app.api.routes.stats import google_maps_urls, haversine
from app.forecast import forecast_fill, linear_fit
from app.rules import evaluate_telemetry, evaluate_urgent, offline_event
from app.schemas import RouteStop
from app.security import (
    create_token,
    decode_token,
    generate_claim_code,
    hash_claim_code,
    hash_password,
    verify_claim_code,
    verify_password,
)

DEVICE = {
    "id": "bin-test01",
    "name": "Площадка №1",
    "address": "ул. Тестовая, 1",
    "last_fill": 90,
    "last_rssi": -60,
    "last_seen": dt.datetime(2026, 9, 22, 12, 0, tzinfo=dt.timezone.utc),
    "status": "active",
}


def test_full_event_once():
    events, state = evaluate_telemetry(DEVICE, {}, fill=85, full_pct=80)
    assert [e.type for e in events] == ["full"]
    assert state["full_active"] is True
    assert events[0].needs_ack

    # повторные данные не должны порождать второе уведомление
    events, state = evaluate_telemetry(DEVICE, state, fill=88, full_pct=80)
    assert events == []


def test_collected_after_full():
    _, state = evaluate_telemetry(DEVICE, {}, fill=90, full_pct=80)
    events, state = evaluate_telemetry(DEVICE, state, fill=6, full_pct=80)
    types = [e.type for e in events]
    assert types == ["collected"]
    assert events[0].resolves == ("full", "full_urgent")
    assert state["full_active"] is False
    assert state["max_fill"] == 6
    assert "last_collection" in state


def test_uncalibrated_device_has_no_fill_events():
    events, state = evaluate_telemetry(DEVICE, {}, fill=None, full_pct=80)
    assert events == []
    assert "max_fill" not in state


def test_urgent_requires_time_and_no_ack():
    long_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).isoformat()
    state = {"full_active": True, "full_since": long_ago, "urgent_sent": False}
    device = {**DEVICE, "last_fill": 97}

    events, new_state = evaluate_urgent(device, state, full_ack_at=None)
    assert [e.type for e in events] == ["full_urgent"]
    assert new_state["urgent_sent"] is True

    # если событие уже подтвердили, срочного уведомления быть не должно
    events, _ = evaluate_urgent(device, state, full_ack_at=dt.datetime.now(dt.timezone.utc))
    assert events == []

    # и если контейнер заполнен недавно
    fresh = {**state, "full_since": dt.datetime.now(dt.timezone.utc).isoformat()}
    events, _ = evaluate_urgent(device, fresh, full_ack_at=None)
    assert events == []


def test_offline_event_message():
    spec = offline_event(DEVICE, 7200)
    assert spec.type == "offline"
    assert "Площадка №1" in spec.message
    assert spec.severity == "warning"


def test_forecast():
    now = dt.datetime.now(dt.timezone.utc)
    points = [(now - dt.timedelta(hours=10 - i), 10.0 + i * 5) for i in range(10)]
    result = forecast_fill(points, current_fill=55, full_pct=80)
    assert result["rate_pct_per_day"] is not None
    assert 4 < result["hours_to_full"] < 6  # растёт на 5 %/час, осталось 25 %
    assert result["eta"] > now


def test_forecast_edge_cases():
    assert forecast_fill([], None, 80)["note"] == "устройство не откалибровано"
    assert forecast_fill([], 90, 80)["hours_to_full"] == 0
    assert forecast_fill([], 10, 80)["note"] == "мало данных для прогноза"
    now = dt.datetime.now(dt.timezone.utc)
    flat = [(now - dt.timedelta(hours=3 - i), 20.0) for i in range(3)]
    assert forecast_fill(flat, 20, 80)["note"] == "заполнение не растёт"
    assert linear_fit(flat) == (0.0, 20.0)


def test_route_links():
    stops = [
        RouteStop(device_id="a", name="A", address="", lat=55.75, lon=37.61, fill=90),
        RouteStop(device_id="b", name="B", address="", lat=55.76, lon=37.62, fill=85),
        RouteStop(device_id="c", name="C", address="", lat=55.77, lon=37.63, fill=95),
    ]
    urls = google_maps_urls(stops)
    assert len(urls) == 1
    assert "origin=55.75,37.61" in urls[0]
    assert "destination=55.77,37.63" in urls[0]
    assert "waypoints=55.76,37.62" in urls[0]
    # длинный список разбивается на несколько ссылок (ограничение Google Maps)
    many = stops * 8
    assert len(google_maps_urls(many)) == 3


def test_haversine():
    # расстояние между Красной площадью и Лужниками — около 7 км
    distance = haversine(55.7539, 37.6208, 55.7158, 37.5535)
    assert 5 < distance < 9


def test_password_hashing():
    stored = hash_password("правильный-пароль")
    assert verify_password("правильный-пароль", stored)
    assert not verify_password("другой", stored)
    assert stored != hash_password("правильный-пароль")  # соль каждый раз новая


def test_claim_codes():
    code = generate_claim_code()
    assert len(code) == 8
    assert "0" not in code and "O" not in code  # похожие символы исключены
    stored = hash_claim_code("bin-a1b2c3", code)
    assert verify_claim_code("bin-a1b2c3", code.lower(), stored)
    assert not verify_claim_code("bin-a1b2c3", "WRONGCODE", stored)
    assert not verify_claim_code("bin-other", code, stored)


def test_jwt():
    token = create_token(7, "admin")
    payload = decode_token(token)
    assert payload["sub"] == "7"
    assert payload["role"] == "admin"
