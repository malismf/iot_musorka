"""Тесты Telegram-бота: привязка чата, команды, подтверждение событий."""
from __future__ import annotations

import datetime as dt

from app.bot import service
from app.security import generate_link_token


async def make_link(pool, user_id: int, minutes: int = 30) -> str:
    token = generate_link_token()
    await pool.execute(
        "INSERT INTO telegram_links(token, user_id, expires_at) VALUES ($1, $2, $3)",
        token,
        user_id,
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes),
    )
    return token


async def test_link_account(pool, client, admin):
    token = await make_link(pool, admin["id"])
    text = await service.link_account(pool, token, chat_id=12345)
    assert "Готово" in text

    user = await pool.fetchrow("SELECT * FROM users WHERE id = $1", admin["id"])
    assert user["telegram_chat_id"] == 12345

    # повторное использование токена запрещено
    again = await service.link_account(pool, token, chat_id=999)
    assert "уже использована" in again

    # действие записано в журнал
    action = await pool.fetchval(
        "SELECT action FROM audit_log WHERE action = 'telegram_link' LIMIT 1"
    )
    assert action == "telegram_link"


async def test_link_errors(pool, client, admin):
    assert "недействительна" in await service.link_account(pool, "нет-такого", 1)
    expired = await make_link(pool, admin["id"], minutes=-1)
    assert "истёк" in await service.link_account(pool, expired, 1)


async def test_commands_require_link(pool):
    assert await service.status_text(pool, 42) == service.NOT_LINKED
    assert await service.bins_text(pool, 42) == service.NOT_LINKED
    text, urls = await service.full_text(pool, 42)
    assert text == service.NOT_LINKED and urls == []


async def test_status_and_lists(pool, client, admin, device):
    device_id = device["device_id"]
    await service.link_account(pool, await make_link(pool, admin["id"]), 500)
    await pool.execute(
        """UPDATE devices
              SET last_fill = 92, online = TRUE, last_seen = now()
            WHERE id = $1""",
        device_id,
    )

    status = await service.status_text(pool, 500)
    assert "Сводка" in status
    assert "Заполнено: 1" in status

    full_text, urls = await service.full_text(pool, 500)
    assert "Площадка №1" in full_text
    assert urls and urls[0].startswith("https://www.google.com/maps/dir/")

    bins = await service.bins_text(pool, 500)
    assert "Площадка №1" in bins and "92%" in bins

    events = await service.events_text(pool, 500)
    assert "Событий пока не было" in events or "привязано" in events


async def test_ack_from_bot(pool, client, admin, device):
    await service.link_account(pool, await make_link(pool, admin["id"]), 600)
    event_id = await pool.fetchval(
        """INSERT INTO events(device_id, type, severity, message, needs_ack)
           VALUES ($1, 'full', 'warning', 'Контейнер заполнен', TRUE) RETURNING id""",
        device["device_id"],
    )

    ok, text = await service.ack_event(pool, event_id, 600)
    assert ok and "Принято" in text
    row = await pool.fetchrow("SELECT * FROM events WHERE id = $1", event_id)
    assert row["acked_by"] == admin["id"]

    missing_ok, missing_text = await service.ack_event(pool, 999999, 600)
    assert not missing_ok and "не найдено" in missing_text


async def test_unlink(pool, client, admin):
    await service.link_account(pool, await make_link(pool, admin["id"]), 700)
    assert "отвязан" in await service.unlink(pool, 700)
    assert await pool.fetchval("SELECT telegram_chat_id FROM users WHERE id = $1", admin["id"]) is None


def test_bot_handlers_registered():
    """Модуль бота импортируется и регистрирует обработчики (aiogram 3)."""
    from app.bot.__main__ import dp

    handlers = dp.message.handlers + dp.callback_query.handlers
    assert len(handlers) >= 7
