"""Работа с MQTT-брокером: выдача учётных данных устройствам и публикация настроек.

Mosquitto с плагином dynamic-security управляется сообщениями в топик
`$CONTROL/dynamic-security/v1`, ответ приходит в `.../v1/response`.
Каждому устройству заводится отдельный клиент и отдельная роль, которая
разрешает писать только в свои топики — чужие сообщения брокер отбросит.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import aiomqtt

from .config import settings

log = logging.getLogger("binsense.mqtt")

CONTROL_TOPIC = "$CONTROL/dynamic-security/v1"
RESPONSE_TOPIC = "$CONTROL/dynamic-security/v1/response"
BACKEND_ROLE = "backend"


def telemetry_topic(device_id: str) -> str:
    return f"{settings.mqtt_topic_prefix}/{device_id}/telemetry"


def event_topic(device_id: str) -> str:
    return f"{settings.mqtt_topic_prefix}/{device_id}/event"


def config_topic(device_id: str) -> str:
    return f"{settings.mqtt_topic_prefix}/{device_id}/config"


def device_role(device_id: str) -> str:
    return f"dev-{device_id}"


class MqttError(RuntimeError):
    pass


class MqttAdmin:
    """Тонкий клиент к dynamic-security + публикация retained-настроек."""

    def __init__(self, identifier: str = "binsense-backend") -> None:
        self.identifier = identifier
        self._lock = asyncio.Lock()

    def _client(self, suffix: str = "") -> aiomqtt.Client:
        return aiomqtt.Client(
            hostname=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_admin_user,
            password=settings.mqtt_admin_password,
            identifier=f"{self.identifier}{suffix}",
            timeout=10,
        )

    # --- низкий уровень ------------------------------------------------------
    async def command(self, commands: list[dict[str, Any]], timeout: float = 10.0) -> list[dict]:
        """Отправляет пакет команд и дожидается ответа брокера."""
        async with self._lock:
            async with self._client("-ctl") as client:
                await client.subscribe(RESPONSE_TOPIC, qos=1)
                await client.publish(
                    CONTROL_TOPIC, json.dumps({"commands": commands}).encode(), qos=1
                )
                try:
                    async with asyncio.timeout(timeout):
                        async for message in client.messages:
                            payload = json.loads(message.payload)
                            return payload.get("responses", [])
                except TimeoutError as exc:  # pragma: no cover - сетевая ошибка
                    raise MqttError("брокер не ответил на команду dynamic-security") from exc
        return []

    @staticmethod
    def _check(responses: list[dict], ignore: tuple[str, ...] = ()) -> None:
        for resp in responses:
            err = resp.get("error")
            if err and not any(part.lower() in err.lower() for part in ignore):
                raise MqttError(f"{resp.get('command')}: {err}")

    async def get_client(self, username: str) -> Optional[dict]:
        """Возвращает описание учётной записи или None, если её нет."""
        responses = await self.command([{"command": "getClient", "username": username}])
        for resp in responses:
            if resp.get("error"):
                if "not found" in resp["error"].lower():
                    return None
                raise MqttError(f"getClient: {resp['error']}")
            return resp.get("data", {}).get("client")
        return None

    # --- инфраструктура ------------------------------------------------------
    async def ensure_backend_role(self) -> None:
        """Роль, позволяющая серверу публиковать настройки устройствам."""
        commands: list[dict[str, Any]] = [
            {"command": "createRole", "rolename": BACKEND_ROLE},
            {
                "command": "addRoleACL",
                "rolename": BACKEND_ROLE,
                "acltype": "publishClientSend",
                "topic": f"{settings.mqtt_topic_prefix}/+/config",
                "allow": True,
            },
        ]
        client = await self.get_client(settings.mqtt_admin_user)
        roles = {r.get("rolename") for r in (client or {}).get("roles", [])}
        if BACKEND_ROLE not in roles:
            # повторный addClientRole брокер считает ошибкой, поэтому проверяем заранее
            commands.append(
                {
                    "command": "addClientRole",
                    "username": settings.mqtt_admin_user,
                    "rolename": BACKEND_ROLE,
                }
            )
        responses = await self.command(commands)
        self._check(responses, ignore=("already exists",))

    # --- устройства ----------------------------------------------------------
    async def provision_device(self, device_id: str, password: str) -> None:
        """Создаёт (или обновляет пароль) учётной записи устройства и его роль."""
        role = device_role(device_id)
        prefix = settings.mqtt_topic_prefix
        commands: list[dict[str, Any]] = [
            {"command": "createRole", "rolename": role},
            {
                "command": "addRoleACL",
                "rolename": role,
                "acltype": "publishClientSend",
                "topic": f"{prefix}/{device_id}/telemetry",
                "allow": True,
            },
            {
                "command": "addRoleACL",
                "rolename": role,
                "acltype": "publishClientSend",
                "topic": f"{prefix}/{device_id}/event",
                "allow": True,
            },
            {
                "command": "addRoleACL",
                "rolename": role,
                "acltype": "subscribeLiteral",
                "topic": f"{prefix}/{device_id}/config",
                "allow": True,
            },
        ]
        client = await self.get_client(device_id)
        if client is None:
            commands.append(
                {
                    "command": "createClient",
                    "username": device_id,
                    "password": password,
                    "roles": [{"rolename": role}],
                }
            )
        else:
            commands.append(
                {"command": "setClientPassword", "username": device_id, "password": password}
            )
            roles = {r.get("rolename") for r in client.get("roles", [])}
            if role not in roles:
                commands.append(
                    {"command": "addClientRole", "username": device_id, "rolename": role}
                )
        responses = await self.command(commands)
        self._check(responses, ignore=("already exists",))
        log.info("устройство %s зарегистрировано в брокере", device_id)

    async def delete_device(self, device_id: str) -> None:
        responses = await self.command(
            [
                {"command": "deleteClient", "username": device_id},
                {"command": "deleteRole", "rolename": device_role(device_id)},
            ]
        )
        self._check(responses, ignore=("not found",))

    async def list_clients(self) -> list[str]:
        responses = await self.command([{"command": "listClients", "count": -1}])
        self._check(responses)
        for resp in responses:
            if resp.get("command") == "listClients":
                return list(resp.get("data", {}).get("clients", []))
        return []

    # --- настройки -----------------------------------------------------------
    async def publish_config(self, device_id: str, config: dict[str, Any]) -> None:
        """Retained-сообщение: спящее устройство получит его сразу после подписки."""
        async with self._client("-cfg") as client:
            await client.publish(
                config_topic(device_id),
                json.dumps(config, ensure_ascii=False).encode(),
                qos=1,
                retain=True,
            )
        log.info("настройки устройства %s опубликованы (ver=%s)", device_id, config.get("ver"))

    async def clear_config(self, device_id: str) -> None:
        async with self._client("-cfg") as client:
            await client.publish(config_topic(device_id), b"", qos=1, retain=True)


mqtt_admin = MqttAdmin()
