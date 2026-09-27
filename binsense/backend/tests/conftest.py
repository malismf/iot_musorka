"""Общие фикстуры тестов.

Тестам нужна только база PostgreSQL (адрес в TEST_DATABASE_URL). Обращения к
MQTT-брокеру подменяются заглушкой, чтобы тесты работали и без него.

Запуск:
    cd backend
    TEST_DATABASE_URL=postgresql://binsense:binsense@localhost:5432/binsense_test \
        python -m pytest -q
"""
from __future__ import annotations

import os

import pytest

TEST_DSN = os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql://binsense:binsense@localhost:5432/binsense_test"
)

# Переменные окружения должны быть выставлены до импорта настроек приложения
os.environ.setdefault("DATABASE_URL", TEST_DSN)
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("PUBLIC_URL", "http://testserver")
os.environ.setdefault("ADMIN_EMAIL", "")
os.environ.setdefault("ADMIN_PASSWORD", "")
os.environ.setdefault("API_METRICS", "false")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import mqtt as mqtt_module  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db import create_pool, migrate  # noqa: E402


class FakeMqtt:
    """Заглушка брокера: запоминает, что сервер пытался опубликовать."""

    def __init__(self) -> None:
        self.provisioned: dict[str, str] = {}
        self.configs: dict[str, dict] = {}
        self.deleted: list[str] = []

    async def ensure_backend_role(self) -> None:
        return None

    async def provision_device(self, device_id: str, password: str) -> None:
        self.provisioned[device_id] = password

    async def delete_device(self, device_id: str) -> None:
        self.deleted.append(device_id)

    async def publish_config(self, device_id: str, config: dict) -> None:
        self.configs[device_id] = config

    async def clear_config(self, device_id: str) -> None:
        self.configs.pop(device_id, None)

    async def list_clients(self) -> list[str]:
        return list(self.provisioned)


@pytest.fixture
def fake_mqtt(monkeypatch) -> FakeMqtt:
    fake = FakeMqtt()
    monkeypatch.setattr(mqtt_module, "mqtt_admin", fake)
    # модули импортировали объект по значению — подменяем и там
    import app.devices as devices_module
    import app.api.routes.admin as admin_module
    import app.ingestor.service as ingestor_module

    monkeypatch.setattr(devices_module, "mqtt_admin", fake)
    monkeypatch.setattr(admin_module, "mqtt_admin", fake)
    monkeypatch.setattr(ingestor_module, "mqtt_admin", fake)
    return fake


@pytest_asyncio.fixture
async def pool():
    pool = await create_pool(TEST_DSN)
    await migrate(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            TRUNCATE events, telemetry, device_metrics, api_requests,
                     audit_log, device_config, devices, users
            RESTART IDENTITY CASCADE
            """
        )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def client(pool):
    app.state.pool = pool
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest_asyncio.fixture
async def admin(client):
    """Первый зарегистрированный пользователь получает роль администратора."""
    response = await client.post(
        "/api/auth/register",
        json={"email": "admin@binsense.test", "password": "admin12345", "name": "Админ"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    client.headers["Authorization"] = f"Bearer {data['access_token']}"
    return data["user"]


@pytest_asyncio.fixture
async def device(client, admin, fake_mqtt):
    """Подготовленное и привязанное устройство."""
    provision = await client.post(
        "/api/admin/devices",
        json={"device_id": "bin-test01", "hw": "test", "fw": "1.0.0"},
    )
    assert provision.status_code == 201, provision.text
    info = provision.json()
    claim = await client.post(
        "/api/devices/claim",
        json={
            "device_id": info["device_id"],
            "claim_code": info["claim_code"],
            "name": "Площадка №1",
            "address": "ул. Тестовая, 1",
            "lat": 55.75,
            "lon": 37.61,
            "volume_l": 1100,
        },
    )
    assert claim.status_code == 201, claim.text
    await client.patch(f"/api/devices/{info['device_id']}", json={"empty_mm": 980, "full_mm": 250})
    return info
