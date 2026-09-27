#!/usr/bin/env python3
"""«Заводская» подготовка устройства BinSense.

Что делает скрипт:
  1. (опционально) заливает прошивку через PlatformIO;
  2. читает идентификатор устройства из его последовательной консоли;
  3. регистрирует устройство на сервере (учётка MQTT + код привязки);
  4. записывает настройки в NVS устройства командой `prov`;
  5. выводит код привязки и ссылку, по которой устройство добавляют в приложении.

Примеры:
    python tools/provision.py --port /dev/ttyUSB0 --api https://bins.example.com --flash
    python tools/provision.py --port COM5 --api https://localhost --mqtt-host 192.168.137.1
    python tools/provision.py --device-id bin-a1b2c3 --api http://localhost:8000   # без железа

Логин и пароль администратора можно задать переменными окружения
BINSENSE_EMAIL и BINSENSE_PASSWORD.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import subprocess
import time
from urllib.parse import urlparse

import httpx

try:  # serial нужен только при работе с реальным устройством
    import serial  # type: ignore
except ImportError:  # pragma: no cover
    serial = None

BAUD = 115200
FIRMWARE_DIR = pathlib.Path(__file__).resolve().parent.parent / "firmware"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Адреса, по которым устройство до брокера не достучится: это сама плата или имя
# контейнера внутри docker-сети.
UNREACHABLE_HOSTS = LOCAL_HOSTS | {"", "mqtt", "0.0.0.0"}


# --- сервер ------------------------------------------------------------------
def login(api: str, email: str, password: str, verify: bool = True) -> httpx.Client:
    client = httpx.Client(base_url=api.rstrip("/") + "/api", timeout=30, verify=verify)
    response = client.post("/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        raise SystemExit(f"Не удалось войти: {response.status_code} {response.text}")
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


def register_device(client: httpx.Client, device_id: str, hw: str, fw: str, reset: bool) -> dict:
    response = client.post(
        "/admin/devices",
        json={"device_id": device_id, "hw": hw, "fw": fw, "reset_claim_code": reset},
    )
    if response.status_code >= 400:
        raise SystemExit(f"Сервер отказал: {response.status_code} {response.text}")
    return response.json()


# --- устройство --------------------------------------------------------------
class DeviceConsole:
    """Последовательная консоль прошивки (см. firmware/src/console.cpp)."""

    def __init__(self, port: str, baud: int = BAUD, timeout: float = 2.0) -> None:
        if serial is None:
            raise SystemExit("Нужен пакет pyserial: pip install pyserial")
        self.ser = serial.Serial(port, baud, timeout=timeout)

    def reset(self) -> None:
        """Сброс платы линиями DTR/RTS, как это делает esptool."""
        self.ser.setDTR(False)
        self.ser.setRTS(True)
        time.sleep(0.15)
        self.ser.setRTS(False)
        time.sleep(0.05)
        self.ser.reset_input_buffer()

    def wait_banner(self, timeout: float = 8.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.ser.readline().decode("utf-8", "replace").strip()
            if line:
                print(f"  < {line}")
            if "BINSENSE CONSOLE" in line:
                return True
        return False

    def command(self, text: str, timeout: float = 3.0) -> list[str]:
        self.ser.reset_input_buffer()
        self.ser.write((text + "\n").encode())
        self.ser.flush()
        lines: list[str] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.ser.readline().decode("utf-8", "replace").strip()
            if not line:
                continue
            lines.append(line)
            if line.startswith(("OK", "ERR")) or line.startswith("{"):
                break
        return lines

    def info(self) -> dict:
        for line in self.command("info"):
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise SystemExit("Устройство не ответило на команду info")

    def provision(self, payload: dict) -> bool:
        lines = self.command("prov " + json.dumps(payload, separators=(",", ":")), timeout=5)
        for line in lines:
            print(f"  < {line}")
        return any(line.startswith("OK") for line in lines)

    def close(self) -> None:
        self.ser.close()


def flash(env: str, port: str) -> None:
    print(f"== Заливаю прошивку (окружение {env})…")
    result = subprocess.run(
        ["pio", "run", "-e", env, "-t", "upload", "--upload-port", port],
        cwd=FIRMWARE_DIR,
    )
    if result.returncode != 0:
        raise SystemExit("Не удалось залить прошивку")


def check_device_host(host: str) -> None:
    """Устройство не должно получить адрес, по которому брокер ему не виден."""
    if host.strip().lower() in UNREACHABLE_HOSTS or host.startswith("127."):
        raise SystemExit(
            f"Адрес брокера «{host}» устройству недоступен. Укажите адрес компьютера с "
            "сервером в локальной сети: --mqtt-host 192.168.x.x (или MQTT_PUBLIC_HOST в .env "
            "и перезапуск api)."
        )


# --- основной сценарий -------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Подготовка устройства BinSense")
    parser.add_argument("--api", default=os.getenv("BINSENSE_API", "http://localhost:8000"))
    parser.add_argument("--email", default=os.getenv("BINSENSE_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("BINSENSE_PASSWORD", ""))
    parser.add_argument("--port", help="последовательный порт устройства, например /dev/ttyUSB0")
    parser.add_argument("--device-id", help="работать без устройства, по известному ID")
    parser.add_argument("--hw", default="esp8266-a02yyuw")
    parser.add_argument("--env", default="esp8266",
                        help="окружение PlatformIO для --flash: esp8266, esp8266_hcsr04")
    parser.add_argument("--flash", action="store_true", help="сначала залить прошивку")
    parser.add_argument("--reset-code", action="store_true", help="выдать новый код привязки")
    parser.add_argument(
        "--mqtt-host", help="адрес брокера для устройства (IP ноутбука при локальном запуске)"
    )
    parser.add_argument("--mqtt-port", type=int)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="не проверять сертификат API (для https://localhost проверка отключается сама)",
    )
    args = parser.parse_args()

    if not args.port and not args.device_id:
        parser.error("укажите --port (устройство подключено) или --device-id")
    if args.port and args.mqtt_host is not None:
        check_device_host(args.mqtt_host)

    # У Caddy на localhost свой самоподписанный сертификат — Python ему не доверяет
    verify = not (args.insecure or urlparse(args.api).hostname in LOCAL_HOSTS)
    email = args.email or input("Почта администратора: ")
    password = args.password or getpass.getpass("Пароль: ")
    client = login(args.api, email, password, verify=verify)
    print(f"== Вход на {args.api} выполнен")

    console = None
    fw_version = ""
    device_id = args.device_id
    hw = args.hw

    if args.port:
        if args.flash:
            flash(args.env, args.port)
        console = DeviceConsole(args.port)
        print("== Сбрасываю плату и жду консоль…")
        console.reset()
        if not console.wait_banner():
            raise SystemExit(
                "Не дождался приглашения консоли. Проверьте порт и нажмите кнопку RESET."
            )
        info = console.info()
        device_id = info.get("id", "")
        fw_version = info.get("fw", "")
        hw = info.get("hw", hw)
        print(f"== Устройство: {device_id} (fw {fw_version}, {hw})")

    if not device_id:
        raise SystemExit("Не удалось определить идентификатор устройства")

    data = register_device(client, device_id, hw, fw_version, args.reset_code)
    print(f"== Зарегистрировано на сервере: {data['device_id']}")
    if data["claim_code"]:
        print(f"   код привязки: {data['claim_code']}")
    else:
        print("   код привязки прежний (используйте --reset-code, чтобы выдать новый)")

    if console is not None:
        host = args.mqtt_host or data["mqtt_host"]
        check_device_host(host)
        payload = {
            "host": host,
            "port": args.mqtt_port or data["mqtt_port"],
            "user": data["mqtt_username"],
            "pass": data["mqtt_password"],
        }
        print(f"== Записываю настройки в устройство (брокер {host}:{payload['port']})…")
        if not console.provision(payload):
            raise SystemExit("Устройство не приняло настройки (команда prov)")
        console.command("exit")  # иначе консоль ждёт следующую команду ещё две минуты
        print("== Устройство настроено")
        console.close()

    if data["claim_code"]:
        print(f"== Ссылка для привязки: {data['claim_url']}")

    print("\nГотово. Дальше — по инструкции монтажника docs/USER_GUIDE.md:")
    print("  1. подать питание,  2. подключиться к точке доступа BinSense-… и задать Wi-Fi,")
    print("  3. открыть ссылку для привязки или ввести ID и код на странице «Добавить устройство»,")
    print("  4. откалибровать кнопкой на пустом баке.")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
