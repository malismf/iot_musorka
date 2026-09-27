#!/usr/bin/env python3
"""Эмулятор устройств BinSense.

Создаёт несколько виртуальных контейнеров, регистрирует их на сервере
(теми же запросами, что и настоящее устройство) и публикует телеметрию в MQTT
под их собственными учётными записями. Нужен, чтобы разрабатывать сервер и
приложение, пока не готово железо, и чтобы на демонстрации на карте было
несколько точек.

Пример:
    python tools/emulator.py --api http://localhost:8000 --email admin@bins.local \\
        --password admin12345 --mqtt-host localhost --count 12 --speed 120
"""
from __future__ import annotations

import argparse
import getpass
import json
import math
import os
import pathlib
import random
import signal
import sys
import time
from dataclasses import dataclass, field

import httpx
import paho.mqtt.client as mqtt

STREETS = [
    "ул. Ленина", "ул. Гагарина", "пр. Мира", "ул. Советская", "ул. Школьная",
    "ул. Зелёная", "ул. Садовая", "ул. Лесная", "ул. Заводская", "ул. Новая",
    "бул. Победы", "ул. Речная", "пер. Тихий", "ул. Северная", "ул. Южная",
]
STOP = False


@dataclass
class VirtualDevice:
    device_id: str
    password: str
    host: str
    port: int
    fill: float = 0.0
    rate: float = 1.5           # %/час
    seq: int = 0
    boot: int = field(default_factory=lambda: random.randint(1, 10**6))
    cfg_ver: int = 0
    full_pct: int = 80
    delta_pct: int = 3
    heartbeat_s: int = 7200
    interval_s: int = 900
    empty_mm: int = 980
    full_mm: int = 250
    last_sent_fill: float = -100.0
    last_sent_at: float = 0.0
    offline: bool = False
    client: mqtt.Client | None = None

    # --- MQTT ---------------------------------------------------------------
    def connect(self) -> None:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=self.device_id, clean_session=True
        )
        client.username_pw_set(self.device_id, self.password)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.connect(self.host, self.port, keepalive=60)
        client.loop_start()
        self.client = client

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code != 0:
            print(f"[{self.device_id}] не удалось подключиться к брокеру: {reason_code}")
            return
        client.subscribe(f"bins/{self.device_id}/config", qos=1)

    def _on_message(self, client, userdata, message) -> None:
        """Настройки приходят retained-сообщением — как на настоящем устройстве."""
        try:
            config = json.loads(message.payload)
        except json.JSONDecodeError:
            return
        if config.get("ver", 0) <= self.cfg_ver:
            return
        self.cfg_ver = int(config["ver"])
        self.full_pct = int(config.get("full_pct", self.full_pct))
        self.delta_pct = int(config.get("delta_pct", self.delta_pct))
        self.heartbeat_s = int(config.get("heartbeat_s", self.heartbeat_s))
        self.interval_s = int(config.get("interval_s", self.interval_s))
        if config.get("empty_mm"):
            self.empty_mm = int(config["empty_mm"])
        self.full_mm = int(config.get("full_mm", self.full_mm))
        print(f"[{self.device_id}] применил настройки ver={self.cfg_ver}")

    def publish(self, topic: str, payload: dict) -> None:
        if self.client is None or self.offline:
            return
        self.client.publish(
            f"bins/{self.device_id}/{topic}", json.dumps(payload), qos=1
        )

    # --- симуляция -----------------------------------------------------------
    def dist_mm(self) -> int:
        span = self.empty_mm - self.full_mm
        return int(self.empty_mm - span * min(100.0, max(0.0, self.fill)) / 100.0)

    def step(self, sim_seconds: float, sim_now: float) -> None:
        """sim_now — модельное время в секундах от старта эмулятора."""
        hours = sim_seconds / 3600.0
        self.fill = min(100.0, self.fill + self.rate * hours * random.uniform(0.6, 1.4))

        # вывоз мусора: когда контейнер переполнен, приезжает мусоровоз
        if self.fill >= 92 and random.random() < 0.25:
            self.fill = random.uniform(2, 8)
            self.send(sim_now)
            return

        delta = abs(self.fill - self.last_sent_fill)
        if delta >= self.delta_pct or (sim_now - self.last_sent_at) >= self.heartbeat_s:
            self.send(sim_now, wake="timer")

    def send(self, now: float, wake: str = "timer") -> None:
        self.seq += 1
        self.publish(
            "telemetry",
            {
                "seq": self.seq,
                "boot": self.boot,
                "ts": int(time.time()),
                "fill": int(round(self.fill)),
                "dist_mm": self.dist_mm(),
                "rssi": random.randint(-85, -55),
                "wake": wake,
                "wifi_ms": random.randint(700, 2200),
                "mqtt_ms": random.randint(120, 500),
                "fw": "1.0.0-emu",
                "hw": "emulator",
                "cfg_ver": self.cfg_ver,
            },
        )
        self.last_sent_fill = self.fill
        self.last_sent_at = now


# --- регистрация на сервере ---------------------------------------------------
def api_login(api: str, email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=api.rstrip("/") + "/api", timeout=30)
    response = client.post("/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        raise SystemExit(f"Не удалось войти: {response.status_code} {response.text}")
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


def ensure_devices(api_client: httpx.Client, count: int, center, radius_km: float,
                   state_path: pathlib.Path, reset: bool) -> list[dict]:
    state: dict[str, dict] = {}
    if state_path.exists() and not reset:
        state = json.loads(state_path.read_text(encoding="utf-8"))

    devices = []
    for index in range(1, count + 1):
        device_id = f"bin-emu{index:03d}"
        saved = state.get(device_id)
        if saved and not reset:
            devices.append(saved)
            continue

        response = api_client.post(
            "/admin/devices",
            json={"device_id": device_id, "hw": "emulator", "fw": "1.0.0-emu",
                  "reset_claim_code": True},
        )
        response.raise_for_status()
        data = response.json()

        angle = random.uniform(0, 2 * math.pi)
        distance = radius_km * math.sqrt(random.random())
        lat = center[0] + (distance / 111.0) * math.sin(angle)
        lon = center[1] + (distance / (111.0 * math.cos(math.radians(center[0])))) * math.cos(angle)
        claim = api_client.post(
            "/devices/claim",
            json={
                "device_id": device_id,
                "claim_code": data["claim_code"],
                "name": f"Площадка №{index}",
                "address": f"{random.choice(STREETS)}, {random.randint(1, 80)}",
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "volume_l": random.choice([660, 770, 1100]),
            },
        )
        if claim.status_code >= 400 and claim.status_code != 409:
            raise SystemExit(f"Не удалось привязать {device_id}: {claim.text}")
        # эмулятор сразу «откалиброван»: сообщаем глубину контейнера
        api_client.patch(f"/devices/{device_id}", json={"empty_mm": 980, "full_mm": 250})
        data["lat"], data["lon"] = lat, lon
        state[device_id] = data
        devices.append(data)
        print(f"создано устройство {device_id}")

    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return devices


def main() -> None:
    parser = argparse.ArgumentParser(description="Эмулятор устройств BinSense")
    parser.add_argument("--api", default=os.getenv("BINSENSE_API", "http://localhost:8000"))
    parser.add_argument("--email", default=os.getenv("BINSENSE_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("BINSENSE_PASSWORD", ""))
    parser.add_argument("--mqtt-host", default=os.getenv("MQTT_HOST", "localhost"))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--center", default="55.7558,37.6173", help="центр района, lat,lon")
    parser.add_argument("--radius-km", type=float, default=2.0)
    parser.add_argument("--speed", type=float, default=120.0,
                        help="во сколько раз время идёт быстрее реального")
    parser.add_argument("--tick", type=float, default=3.0, help="шаг симуляции, реальных секунд")
    parser.add_argument("--state", default="tools/.emulator_state.json")
    parser.add_argument("--reset", action="store_true", help="перевыдать устройства заново")
    parser.add_argument("--once", action="store_true", help="отправить один пакет и выйти")
    args = parser.parse_args()

    email = args.email or input("Почта администратора: ")
    password = args.password or getpass.getpass("Пароль: ")
    api_client = api_login(args.api, email, password)
    center = tuple(float(x) for x in args.center.split(","))

    registered = ensure_devices(
        api_client, args.count, center, args.radius_km, pathlib.Path(args.state), args.reset
    )

    devices: list[VirtualDevice] = []
    for index, data in enumerate(registered):
        device = VirtualDevice(
            device_id=data["device_id"],
            password=data["mqtt_password"],
            host=args.mqtt_host,
            port=args.mqtt_port,
            fill=random.uniform(0, 70),
            rate=random.uniform(0.6, 4.0),
        )
        # пара «нештатных» устройств для демонстрации уведомлений
        if index == 3 and len(registered) > 4:
            device.offline = True
        device.connect()
        devices.append(device)

    time.sleep(1.0)
    print(f"эмулятор запущен: {len(devices)} устройств, ускорение ×{args.speed:g}")

    def handle_stop(*_):
        global STOP
        STOP = True

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    sim_now = 0.0
    for device in devices:
        device.send(sim_now, wake="boot")
    if args.once:
        time.sleep(2)
        return

    while not STOP:
        time.sleep(args.tick)
        sim_seconds = args.tick * args.speed
        sim_now += sim_seconds
        for device in devices:
            device.step(sim_seconds, sim_now)

    for device in devices:
        if device.client is not None:
            device.client.loop_stop()
            device.client.disconnect()
    print("эмулятор остановлен")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
