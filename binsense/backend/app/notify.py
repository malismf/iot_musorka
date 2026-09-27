"""Отправка уведомлений пользователям (Telegram Bot API)."""
from __future__ import annotations

import datetime as dt
import html
import logging
from typing import Any, Optional

import httpx

from .config import settings
from .rules import ICONS

log = logging.getLogger("binsense.notify")

TYPE_TITLES = {
    "full": "Контейнер заполнен",
    "full_urgent": "Срочно вывезти",
    "collected": "Контейнер вывезен",
    "offline": "Нет связи",
    "online": "Снова в сети",
    "sensor_error": "Сбой датчика",
    "calibrated": "Калибровка",
    "hello": "Устройство включено",
}


def format_event(event_type: str, message: str, data: dict[str, Any], device=None) -> str:
    icon = ICONS.get(event_type, "ℹ️")
    title = TYPE_TITLES.get(event_type, event_type)
    lines = [f"{icon} <b>{html.escape(title)}</b>", html.escape(message)]

    details = []
    if device is not None:
        if device["last_fill"] is not None:
            details.append(f"заполнено {device['last_fill']}%")
        if device["last_rssi"] is not None:
            details.append(f"Wi-Fi {device['last_rssi']} dBm")
    if details:
        lines.append(html.escape(" · ".join(details)))

    lines.append(dt.datetime.now().strftime("%d.%m.%Y %H:%M"))
    return "\n".join(lines)


class TelegramClient:
    """Минимальный клиент Bot API: ingestor шлёт уведомления без aiogram."""

    def __init__(self, token: str = "", api_base: str = "") -> None:
        self.token = token or settings.telegram_bot_token
        self.api_base = (api_base or settings.telegram_api_base).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call(self, method: str, **payload: Any) -> dict:
        if not self.enabled:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")
        client = await self._http()
        url = f"{self.api_base}/bot{self.token}/{method}"
        response = await client.post(url, json=payload)
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data.get('description')}")
        return data.get("result", {})

    async def send_message(
        self, chat_id: int, text: str, buttons: Optional[list[list[dict]]] = None
    ) -> dict:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        return await self.call("sendMessage", **payload)


def event_buttons(event_id: int, device_id: Optional[str], needs_ack: bool) -> list[list[dict]]:
    row: list[dict] = []
    if needs_ack:
        row.append({"text": "✅ Принято", "callback_data": f"ack:{event_id}"})
    url = settings.public_url.rstrip("/")
    # Telegram принимает только публичные https-ссылки в кнопках
    if device_id and url.startswith("https://") and "localhost" not in url:
        row.append({"text": "🗺 На карте", "url": f"{url}/devices/{device_id}"})
    return [row] if row else []


async def notify_event(
    pool,
    telegram: TelegramClient,
    event_id: int,
    event_type: str,
    severity: str,
    message: str,
    data: dict,
    device,
    audience: tuple[str, ...],
    needs_ack: bool = False,
) -> int:
    """Рассылает событие подписчикам и записывает результат в notifications."""
    if not audience:
        return 0
    recipients = await pool.fetch(
        """
        SELECT id, telegram_chat_id
          FROM users
         WHERE telegram_chat_id IS NOT NULL
           AND notify_enabled
           AND role = ANY($1::text[])
           AND ($2 <> 'info' OR notify_info)
        """,
        list(audience),
        severity,
    )
    if not recipients:
        return 0
    if not telegram.enabled:
        for user in recipients:
            await pool.execute(
                """INSERT INTO notifications(event_id, user_id, channel, status, error)
                   VALUES ($1, $2, 'telegram', 'skipped', 'бот не настроен')""",
                event_id,
                user["id"],
            )
        return 0

    text = format_event(event_type, message, data, device)
    buttons = event_buttons(event_id, device["id"] if device is not None else None, needs_ack)
    sent = 0
    for user in recipients:
        try:
            result = await telegram.send_message(user["telegram_chat_id"], text, buttons)
            await pool.execute(
                """INSERT INTO notifications(event_id, user_id, channel, status, tg_message_id)
                   VALUES ($1, $2, 'telegram', 'sent', $3)""",
                event_id,
                user["id"],
                result.get("message_id"),
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001 — уведомления не должны ронять ingestor
            log.warning("не удалось отправить уведомление пользователю %s: %s", user["id"], exc)
            await pool.execute(
                """INSERT INTO notifications(event_id, user_id, channel, status, error)
                   VALUES ($1, $2, 'telegram', 'failed', $3)""",
                event_id,
                user["id"],
                str(exc)[:500],
            )
    return sent
