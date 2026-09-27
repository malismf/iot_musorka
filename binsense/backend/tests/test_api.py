"""Тесты HTTP API: регистрация, выдача устройств, привязка, настройки, события."""
from __future__ import annotations


async def test_public_config_available_without_auth(client):
    response = await client.get("/api/config/public")
    assert response.status_code == 200
    data = response.json()
    assert len(data["map_center"]) == 2
    assert data["version"]


async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["db"] is True


async def test_register_login_and_me(client):
    register = await client.post(
        "/api/auth/register",
        json={"email": "First@Example.com", "password": "password123", "name": "Первый"},
    )
    assert register.status_code == 201
    assert register.json()["user"]["role"] == "admin"  # первый пользователь — администратор
    assert register.json()["user"]["email"] == "first@example.com"

    duplicate = await client.post(
        "/api/auth/register",
        json={"email": "first@example.com", "password": "password123"},
    )
    assert duplicate.status_code == 409

    second = await client.post(
        "/api/auth/register",
        json={"email": "second@example.com", "password": "password123"},
    )
    assert second.json()["user"]["role"] == "dispatcher"

    login = await client.post(
        "/api/auth/login", json={"email": "first@example.com", "password": "password123"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    wrong = await client.post(
        "/api/auth/login", json={"email": "first@example.com", "password": "неверный"}
    )
    assert wrong.status_code == 401

    me = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "first@example.com"

    assert (await client.get("/api/devices")).status_code == 401  # без токена нельзя


async def test_provision_creates_credentials(client, admin, fake_mqtt):
    response = await client.post(
        "/api/admin/devices", json={"device_id": "BIN-AbC123", "hw": "esp8266-a02yyuw"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["device_id"] == "bin-abc123"  # идентификатор приводится к нижнему регистру
    assert len(data["claim_code"]) == 8
    assert data["mqtt_password"]
    assert data["claim_url"].endswith(f"id={data['device_id']}&code={data['claim_code']}")
    # устройство заведено в брокере и получило retained-настройки
    assert fake_mqtt.provisioned["bin-abc123"] == data["mqtt_password"]
    assert fake_mqtt.configs["bin-abc123"]["claimed"] is False


async def test_claim_flow(client, admin, fake_mqtt):
    provision = (
        await client.post("/api/admin/devices", json={"device_id": "bin-claim1"})
    ).json()

    bad = await client.post(
        "/api/devices/claim",
        json={"device_id": "bin-claim1", "claim_code": "WRONG123", "name": "Тест"},
    )
    assert bad.status_code == 400

    missing = await client.post(
        "/api/devices/claim",
        json={"device_id": "bin-nope", "claim_code": "WRONG123", "name": "Тест"},
    )
    assert missing.status_code == 404

    good = await client.post(
        "/api/devices/claim",
        json={
            "device_id": "bin-claim1",
            "claim_code": provision["claim_code"].lower(),  # регистр не важен
            "name": "Площадка №7",
            "address": "ул. Ленина, 7",
            "lat": 55.75,
            "lon": 37.61,
        },
    )
    assert good.status_code == 201
    device = good.json()
    assert device["status"] == "active"
    assert device["name"] == "Площадка №7"
    assert fake_mqtt.configs["bin-claim1"]["claimed"] is True

    again = await client.post(
        "/api/devices/claim",
        json={
            "device_id": "bin-claim1",
            "claim_code": provision["claim_code"],
            "name": "Ещё раз",
        },
    )
    assert again.status_code == 409  # повторная привязка запрещена

    events = (await client.get("/api/devices/bin-claim1/events")).json()
    assert any(event["type"] == "claimed" for event in events)


async def test_claim_bruteforce_locks(client, admin, fake_mqtt):
    await client.post("/api/admin/devices", json={"device_id": "bin-brute"})
    for _ in range(10):
        response = await client.post(
            "/api/devices/claim",
            json={"device_id": "bin-brute", "claim_code": "AAAAAAAA", "name": "x"},
        )
        assert response.status_code == 400
    blocked = await client.post(
        "/api/devices/claim",
        json={"device_id": "bin-brute", "claim_code": "AAAAAAAA", "name": "x"},
    )
    assert blocked.status_code == 429


async def test_update_device_bumps_config(client, device, fake_mqtt):
    device_id = device["device_id"]
    before = (await client.get(f"/api/devices/{device_id}")).json()

    response = await client.patch(
        f"/api/devices/{device_id}",
        json={"name": "Новое имя", "full_pct": 70, "interval_s": 600, "empty_mm": 1000},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Новое имя"
    assert updated["config"]["full_pct"] == 70
    assert updated["empty_mm"] == 1000
    assert updated["config_version"] > before["config_version"]

    published = fake_mqtt.configs[device_id]
    assert published["full_pct"] == 70
    assert published["interval_s"] == 600
    assert published["empty_mm"] == 1000
    assert published["ver"] == updated["config_version"]


async def test_update_without_device_changes_keeps_version(client, device, fake_mqtt):
    device_id = device["device_id"]
    before = (await client.get(f"/api/devices/{device_id}")).json()
    published_before = dict(fake_mqtt.configs.get(device_id, {}))

    # название и место живут только на сервере, остальное совпадает с текущим
    response = await client.patch(
        f"/api/devices/{device_id}",
        json={
            "name": "Площадка у школы",
            "address": "ул. Школьная, 3",
            "lat": 55.7,
            "lon": 37.6,
            "full_pct": before["config"]["full_pct"],
            "interval_s": before["config"]["interval_s"],
            "empty_mm": before["empty_mm"],
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Площадка у школы"
    assert updated["lat"] == 55.7
    assert updated["config_version"] == before["config_version"]
    assert fake_mqtt.configs.get(device_id, {}) == published_before


async def test_unclaim(client, device, fake_mqtt):
    device_id = device["device_id"]
    response = await client.delete(f"/api/devices/{device_id}/claim")
    assert response.status_code == 200
    assert response.json()["status"] == "unclaimed"
    assert fake_mqtt.configs[device_id]["claimed"] is False

    # неактивные устройства не попадают в общий список
    listed = (await client.get("/api/devices")).json()
    assert all(item["id"] != device_id for item in listed)
    listed_all = (await client.get("/api/devices", params={"include_unclaimed": True})).json()
    assert any(item["id"] == device_id for item in listed_all)


async def test_permissions_for_driver(client, device, pool):
    await client.post(
        "/api/auth/register",
        json={"email": "driver@binsense.test", "password": "password123", "name": "Водитель"},
    )
    await pool.execute("UPDATE users SET role = 'driver' WHERE email = 'driver@binsense.test'")
    login = await client.post(
        "/api/auth/login", json={"email": "driver@binsense.test", "password": "password123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (await client.get("/api/devices", headers=headers)).status_code == 200
    forbidden = await client.patch(
        f"/api/devices/{device['device_id']}", json={"name": "Нельзя"}, headers=headers
    )
    assert forbidden.status_code == 403
    assert (await client.get("/api/admin/users", headers=headers)).status_code == 403


async def test_events_ack_and_stats(client, device, pool):
    device_id = device["device_id"]
    await pool.execute(
        """INSERT INTO events(device_id, type, severity, message, needs_ack)
           VALUES ($1, 'full', 'warning', 'Контейнер заполнен', TRUE)""",
        device_id,
    )
    events = (await client.get("/api/events", params={"only_open": True})).json()
    assert len(events) == 1
    event_id = events[0]["id"]

    stats = (await client.get("/api/stats/overview")).json()
    assert stats["open_events"] == 1
    assert stats["active"] == 1

    acked = (await client.post(f"/api/events/{event_id}/ack")).json()
    assert acked["acked_at"] is not None
    assert acked["acked_by_name"] == "Админ"
    assert (await client.get("/api/stats/overview")).json()["open_events"] == 0


async def test_telemetry_history_and_route(client, device, pool):
    device_id = device["device_id"]
    for index, fill in enumerate([10, 40, 85]):
        await pool.execute(
            """INSERT INTO telemetry(device_id, ts, fill, dist_mm, rssi, seq, boot_id)
               VALUES ($1, now() - make_interval(mins => $2), $3, 500, -60, $4, 1)""",
            device_id,
            30 - index * 10,
            fill,
            index,
        )
    await pool.execute("UPDATE devices SET last_fill = 85 WHERE id = $1", device_id)

    raw = (await client.get(f"/api/devices/{device_id}/telemetry")).json()
    assert len(raw) == 3
    hourly = (
        await client.get(f"/api/devices/{device_id}/telemetry", params={"bucket": "1h"})
    ).json()
    assert len(hourly) <= 2
    assert hourly[0]["fill"] is not None

    route = (await client.get("/api/route", params={"min_fill": 80})).json()
    assert [stop["device_id"] for stop in route["stops"]] == [device_id]
    assert route["map_urls"]


async def test_admin_users_and_audit(client, admin, device):
    users = (await client.get("/api/admin/users")).json()
    assert len(users) == 1

    audit = (await client.get("/api/admin/audit")).json()
    actions = {row["action"] for row in audit}
    assert {"register", "login", "provision", "claim"} <= actions


async def test_openapi_schema(client):
    schema = (await client.get("/api/openapi.json")).json()
    assert schema["info"]["title"] == "BinSense API"
    assert "/api/devices/claim" in schema["paths"]
