"""Тесты правил и вспомогательных функций (без базы и брокера)."""
from __future__ import annotations

import datetime as dt

from app.api.routes.stats import google_maps_urls, haversine
from app.devices import build_config_payload
from app.rules import evaluate_telemetry, offline_event
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
    assert events[0].resolves == ("full",)
    assert state["full_active"] is False
    assert state["max_fill"] == 6


def test_uncalibrated_device_has_no_fill_events():
    events, state = evaluate_telemetry(DEVICE, {}, fill=None, full_pct=80)
    assert events == []
    assert "max_fill" not in state


def test_offline_event_message():
    spec = offline_event(DEVICE, 7200)
    assert spec.type == "offline"
    assert "Площадка №1" in spec.message
    assert spec.severity == "warning"


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
    token = create_token(7)
    payload = decode_token(token)
    assert payload["sub"] == "7"


def test_config_payload_fields():
    device = {"status": "active", "empty_mm": 980, "full_mm": 250}
    # ключи, оставшиеся в базе от старых версий, устройству не уходят
    stored = {"interval_s": 60, "night_start": 23, "tz": "MSK-3"}
    payload = build_config_payload(device, 5, stored)
    assert set(payload) == {
        "ver", "claimed", "interval_s", "heartbeat_s", "full_interval_s",
        "full_pct", "delta_pct", "samples", "empty_mm", "full_mm",
    }
    assert payload["interval_s"] == 60
    assert payload["claimed"] is True
