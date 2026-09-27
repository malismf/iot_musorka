"""Тесты ingestor: приём телеметрии, дубли, потери, события и уведомления."""
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from app.ingestor.service import Ingestor
from app.notify import TelegramClient


class FakeTelegram(TelegramClient):
    """Вместо обращения к Telegram запоминает сообщения."""

    def __init__(self) -> None:
        super().__init__(token="fake-token", api_base="http://localhost")
        self.sent: list[tuple[int, str, list | None]] = []

    async def send_message(self, chat_id: int, text: str, buttons=None) -> dict:
        self.sent.append((chat_id, text, buttons))
        return {"message_id": len(self.sent)}


@pytest_asyncio.fixture
async def telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest_asyncio.fixture
async def ingestor(pool, telegram, fake_mqtt) -> Ingestor:
    return Ingestor(pool, telegram)


def telemetry(**overrides) -> bytes:
    payload = {
        "seq": 1,
        "boot": 100,
        "fill": 20,
        "dist_mm": 834,
        "rssi": -62,
        "wake": "timer",
        "wake_ms": 2800,
        "wifi_ms": 1100,
        "mqtt_ms": 250,
        "fw": "1.0.0",
        "cfg_ver": 3,
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


async def subscribe_user(pool, role: str = "dispatcher", chat_id: int = 555) -> int:
    return await pool.fetchval(
        """INSERT INTO users(email, password_hash, name, role, telegram_chat_id)
           VALUES ($1, 'x', 'Диспетчер', $2, $3) RETURNING id""",
        f"{role}-{chat_id}@binsense.test",
        role,
        chat_id,
    )


async def test_telemetry_is_stored(ingestor, pool, device):
    device_id = device["device_id"]
    assert await ingestor.handle_telemetry(device_id, telemetry())

    row = await pool.fetchrow("SELECT * FROM telemetry WHERE device_id = $1", device_id)
    assert row["fill"] == 20
    assert row["dist_mm"] == 834

    updated = await pool.fetchrow("SELECT * FROM devices WHERE id = $1", device_id)
    assert updated["last_fill"] == 20
    assert updated["online"] is True
    assert updated["fw"] == "1.0.0"

    metrics = await pool.fetchrow("SELECT * FROM device_metrics WHERE device_id = $1", device_id)
    assert metrics["wake_ms"] == 2800
    assert metrics["lost"] == 0

    # устройство подтвердило версию настроек
    config = await pool.fetchrow("SELECT * FROM device_config WHERE device_id = $1", device_id)
    assert config["applied_version"] == 3


async def test_old_firmware_fields_are_ignored(ingestor, pool, device):
    # старая прошивка присылала счётчик крышки и напряжение батареи — такие
    # сообщения не теряем, лишние поля просто не сохраняются
    device_id = device["device_id"]
    old = telemetry(lid_opens=3, wake="lid", bat_v=3.3)
    assert await ingestor.handle_telemetry(device_id, old)
    row = await pool.fetchrow("SELECT * FROM telemetry WHERE device_id = $1", device_id)
    assert row["fill"] == 20
    assert "lid_opens" not in row.keys() and "bat_v" not in row.keys()
    # и события о разряде не появляется, даже при низком напряжении
    types = await pool.fetch("SELECT type FROM events WHERE device_id = $1", device_id)
    assert "low_battery" not in {r["type"] for r in types}


async def test_duplicate_is_ignored(ingestor, pool, device):
    device_id = device["device_id"]
    assert await ingestor.handle_telemetry(device_id, telemetry(seq=5))
    assert not await ingestor.handle_telemetry(device_id, telemetry(seq=5))
    assert await pool.fetchval("SELECT count(*) FROM telemetry WHERE device_id = $1", device_id) == 1


async def test_sequence_gap_counts_losses(ingestor, pool, device):
    device_id = device["device_id"]
    await ingestor.handle_telemetry(device_id, telemetry(seq=10))
    await ingestor.handle_telemetry(device_id, telemetry(seq=13))
    lost = await pool.fetchval(
        "SELECT lost FROM device_metrics WHERE device_id = $1 ORDER BY id DESC LIMIT 1", device_id
    )
    assert lost == 2


async def test_unknown_device_and_bad_payload(ingestor, device):
    assert not await ingestor.handle_telemetry("bin-unknown", telemetry())
    assert not await ingestor.handle_telemetry(device["device_id"], b"{not json")


async def test_full_event_notifies_subscribers(ingestor, pool, device, telegram):
    device_id = device["device_id"]
    chat_id = 777
    await subscribe_user(pool, "dispatcher", chat_id)

    await ingestor.handle_telemetry(device_id, telemetry(seq=1, fill=20))
    assert telegram.sent == []

    await ingestor.handle_telemetry(device_id, telemetry(seq=2, fill=88))
    assert len(telegram.sent) == 1
    sent_chat, text, buttons = telegram.sent[0]
    assert sent_chat == chat_id
    assert "заполнен" in text.lower()
    assert buttons[0][0]["callback_data"].startswith("ack:")

    event = await pool.fetchrow(
        "SELECT * FROM events WHERE device_id = $1 AND type = 'full'", device_id
    )
    assert event["needs_ack"] is True
    notification = await pool.fetchrow(
        "SELECT * FROM notifications WHERE event_id = $1", event["id"]
    )
    assert notification["status"] == "sent"


async def test_info_events_only_for_subscribed_users(ingestor, pool, device, telegram):
    device_id = device["device_id"]
    await subscribe_user(pool, "dispatcher", 111)  # notify_info по умолчанию выключен
    await ingestor.handle_telemetry(device_id, telemetry(seq=1, fill=90))
    await ingestor.handle_telemetry(device_id, telemetry(seq=2, fill=5))  # вывоз

    types = [
        row["type"]
        for row in await pool.fetch("SELECT type FROM events WHERE device_id = $1", device_id)
    ]
    assert "collected" in types
    # ушло только предупреждение о заполнении, информационное — нет
    assert len(telegram.sent) == 1

    await pool.execute("UPDATE users SET notify_info = TRUE WHERE telegram_chat_id = 111")
    await ingestor.handle_telemetry(device_id, telemetry(seq=3, fill=95))
    await ingestor.handle_telemetry(device_id, telemetry(seq=4, fill=4))
    assert any("вывезен" in text.lower() for _, text, _ in telegram.sent)


async def test_calibration_event_updates_device(ingestor, pool, device, fake_mqtt):
    device_id = device["device_id"]
    version_before = fake_mqtt.configs[device_id]["ver"]

    payload = json.dumps({"type": "calibrated", "empty_mm": 1234, "full_mm": 300}).encode()
    assert await ingestor.handle_event(device_id, payload)

    row = await pool.fetchrow("SELECT empty_mm, full_mm FROM devices WHERE id = $1", device_id)
    assert row["empty_mm"] == 1234
    assert row["full_mm"] == 300
    # настройки переизданы, чтобы устройство и сервер считали заполненность одинаково
    assert fake_mqtt.configs[device_id]["ver"] > version_before
    assert fake_mqtt.configs[device_id]["empty_mm"] == 1234

    event = await pool.fetchrow(
        "SELECT * FROM events WHERE device_id = $1 AND type = 'calibrated'", device_id
    )
    assert "123 см" in event["message"]


async def test_sensor_error_event(ingestor, pool, device, telegram):
    await subscribe_user(pool, "admin", 999)
    payload = json.dumps({"type": "error", "code": "SENSOR_TIMEOUT"}).encode()
    await ingestor.handle_event(device["device_id"], payload)
    event = await pool.fetchrow("SELECT * FROM events WHERE type = 'sensor_error'")
    assert event["data"]["code"] == "SENSOR_TIMEOUT"
    assert len(telegram.sent) == 1


async def test_offline_detection(ingestor, pool, device, telegram):
    device_id = device["device_id"]
    await subscribe_user(pool, "dispatcher", 222)
    await ingestor.handle_telemetry(device_id, telemetry())
    assert await pool.fetchval("SELECT online FROM devices WHERE id = $1", device_id)

    # делаем вид, что данных не было четыре часа (heartbeat 2 часа × 1.5)
    await pool.execute(
        "UPDATE devices SET last_seen = now() - interval '4 hours' WHERE id = $1", device_id
    )
    assert await ingestor.check_offline() == 1
    assert not await pool.fetchval("SELECT online FROM devices WHERE id = $1", device_id)
    assert await pool.fetchval("SELECT count(*) FROM events WHERE type = 'offline'") == 1
    assert any("нет связи" in text.lower() for _, text, _ in telegram.sent)

    # повторный вызов не плодит события
    assert await ingestor.check_offline() == 0

    # когда устройство вернулось, событие закрывается
    await ingestor.handle_telemetry(device_id, telemetry(seq=2))
    online_event = await pool.fetchrow("SELECT * FROM events WHERE type = 'online'")
    assert online_event is not None
    offline_event = await pool.fetchrow("SELECT * FROM events WHERE type = 'offline'")
    assert offline_event["resolved_at"] is not None


async def test_urgent_escalation(ingestor, pool, device, telegram):
    device_id = device["device_id"]
    await subscribe_user(pool, "dispatcher", 333)
    await ingestor.handle_telemetry(device_id, telemetry(fill=97))
    assert await ingestor.check_urgent() == 0  # ещё не прошло два часа

    await pool.execute(
        """UPDATE devices
              SET state = jsonb_set(state, '{full_since}',
                                    to_jsonb((now() - interval '3 hours')::text))
            WHERE id = $1""",
        device_id,
    )
    assert await ingestor.check_urgent() == 1
    event = await pool.fetchrow("SELECT * FROM events WHERE type = 'full_urgent'")
    assert event["severity"] == "critical"
    # второй раз не повторяем
    assert await ingestor.check_urgent() == 0


async def test_cleanup_removes_old_rows(ingestor, pool, device):
    device_id = device["device_id"]
    await pool.execute(
        """INSERT INTO telemetry(device_id, ts, received_at, fill)
           VALUES ($1, now() - interval '400 days', now() - interval '400 days', 10)""",
        device_id,
    )
    await pool.execute(
        """INSERT INTO device_metrics(device_id, ts, latency_ms)
           VALUES ($1, now() - interval '90 days', 100)""",
        device_id,
    )
    await ingestor.cleanup()
    assert await pool.fetchval("SELECT count(*) FROM telemetry") == 0
    assert await pool.fetchval("SELECT count(*) FROM device_metrics") == 0


@pytest.mark.parametrize("topic_suffix", ["telemetry", "event"])
async def test_dispatch_routes_topics(ingestor, device, topic_suffix):
    payload = telemetry() if topic_suffix == "telemetry" else json.dumps({"type": "hello"}).encode()
    await ingestor.dispatch(f"bins/{device['device_id']}/{topic_suffix}", payload)
