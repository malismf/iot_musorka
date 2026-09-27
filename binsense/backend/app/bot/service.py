"""Логика Telegram-бота без привязки к aiogram — её удобно тестировать."""
from __future__ import annotations

import datetime as dt
import html
from typing import Optional

from ..api.routes.stats import google_maps_urls
from ..config import settings
from ..devices import log_action
from ..schemas import RouteStop

HELP = (
    "<b>BinSense</b> — мониторинг мусорных контейнеров.\n\n"
    "/status — сводка по системе\n"
    "/full — заполненные контейнеры и маршрут\n"
    "/bins — все контейнеры\n"
    "/events — последние события\n"
    "/unlink — отвязать этот чат\n"
    "/help — эта справка"
)

NOT_LINKED = (
    "Этот чат не привязан к аккаунту.\n"
    "Откройте веб-приложение → Профиль → «Привязать Telegram» и нажмите кнопку."
)


async def user_by_chat(pool, chat_id: int):
    return await pool.fetchrow("SELECT * FROM users WHERE telegram_chat_id = $1", chat_id)


async def link_account(pool, token: str, chat_id: int) -> str:
    """Обрабатывает /start <token>: привязывает чат к пользователю."""
    row = await pool.fetchrow(
        """SELECT l.*, u.email, u.name
             FROM telegram_links l JOIN users u ON u.id = l.user_id
            WHERE l.token = $1""",
        token,
    )
    if row is None:
        return "Ссылка недействительна. Сгенерируйте новую в профиле веб-приложения."
    if row["used_at"] is not None:
        return "Эта ссылка уже использована. Сгенерируйте новую в профиле."
    if row["expires_at"] < dt.datetime.now(dt.timezone.utc):
        return "Срок действия ссылки истёк. Сгенерируйте новую в профиле."

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE users SET telegram_chat_id = NULL WHERE telegram_chat_id = $1", chat_id
            )
            await conn.execute(
                "UPDATE users SET telegram_chat_id = $2 WHERE id = $1", row["user_id"], chat_id
            )
            await conn.execute(
                "UPDATE telegram_links SET used_at = now() WHERE token = $1", token
            )
    await log_action(pool, row["user_id"], "telegram_link", details={"chat_id": chat_id})
    name = row["name"] or row["email"]
    return (
        f"✅ Готово, {html.escape(name)}!\n"
        "Теперь уведомления о заполнении, разряде и потере связи будут приходить сюда.\n\n"
        + HELP
    )


async def unlink(pool, chat_id: int) -> str:
    user = await user_by_chat(pool, chat_id)
    if user is None:
        return NOT_LINKED
    await pool.execute("UPDATE users SET telegram_chat_id = NULL WHERE id = $1", user["id"])
    await log_action(pool, user["id"], "telegram_unlink", details={"chat_id": chat_id})
    return "Чат отвязан. Уведомления приходить не будут."


async def status_text(pool, chat_id: int) -> str:
    user = await user_by_chat(pool, chat_id)
    if user is None:
        return NOT_LINKED
    row = await pool.fetchrow(
        """
        SELECT count(*) FILTER (WHERE status = 'active') AS active,
               count(*) FILTER (WHERE status = 'active' AND online) AS online,
               count(*) FILTER (WHERE status = 'active' AND NOT online) AS offline,
               count(*) FILTER (WHERE status = 'active'
                                AND last_fill >= COALESCE((c.config ->> 'full_pct')::int, $1)
                               ) AS full,
               avg(last_fill) FILTER (WHERE status = 'active') AS avg_fill
          FROM devices d LEFT JOIN device_config c ON c.device_id = d.id
        """,
        settings.default_full_pct,
    )
    open_events = await pool.fetchval(
        "SELECT count(*) FROM events WHERE needs_ack AND acked_at IS NULL"
    )
    avg_fill = f"{row['avg_fill']:.0f}%" if row["avg_fill"] is not None else "—"
    return (
        "<b>Сводка</b>\n"
        f"Контейнеров: {row['active']}\n"
        f"🟠 Заполнено: {row['full']}\n"
        f"📶 На связи: {row['online']} · 📡 нет связи: {row['offline']}\n"
        f"Средняя заполненность: {avg_fill}\n"
        f"Неподтверждённых событий: {open_events}"
    )


async def full_text(pool, chat_id: int) -> tuple[str, list[str]]:
    user = await user_by_chat(pool, chat_id)
    if user is None:
        return NOT_LINKED, []
    rows = await pool.fetch(
        """
        SELECT d.id, d.name, d.address, d.lat, d.lon, d.last_fill, d.last_seen
          FROM devices d LEFT JOIN device_config c ON c.device_id = d.id
         WHERE d.status = 'active'
           AND d.last_fill >= COALESCE((c.config ->> 'full_pct')::int, $1)
         ORDER BY d.last_fill DESC
        """,
        settings.default_full_pct,
    )
    if not rows:
        return "Заполненных контейнеров нет 👍", []

    lines = [f"<b>Заполненные контейнеры: {len(rows)}</b>"]
    stops: list[RouteStop] = []
    for row in rows:
        title = html.escape(row["name"] or row["id"])
        address = f" — {html.escape(row['address'])}" if row["address"] else ""
        lines.append(f"🟠 {row['last_fill']}% · {title}{address}")
        if row["lat"] is not None and row["lon"] is not None:
            stops.append(
                RouteStop(
                    device_id=row["id"],
                    name=row["name"],
                    address=row["address"],
                    lat=row["lat"],
                    lon=row["lon"],
                    fill=row["last_fill"],
                )
            )
    urls = google_maps_urls(stops)
    return "\n".join(lines), urls


async def bins_text(pool, chat_id: int) -> str:
    user = await user_by_chat(pool, chat_id)
    if user is None:
        return NOT_LINKED
    rows = await pool.fetch(
        """
        SELECT id, name, address, last_fill, online, last_seen
          FROM devices WHERE status = 'active'
         ORDER BY last_fill DESC NULLS LAST, name
         LIMIT 50
        """
    )
    if not rows:
        return "Пока нет ни одного привязанного устройства."
    lines = ["<b>Контейнеры</b>"]
    for row in rows:
        if not row["online"]:
            icon = "📡"
        elif row["last_fill"] is None:
            icon = "⚪️"
        elif row["last_fill"] >= settings.default_full_pct:
            icon = "🟠"
        elif row["last_fill"] >= 50:
            icon = "🟡"
        else:
            icon = "🟢"
        fill = f"{row['last_fill']}%" if row["last_fill"] is not None else "нет калибровки"
        lines.append(f"{icon} {fill} · {html.escape(row['name'] or row['id'])}")
    return "\n".join(lines)


async def events_text(pool, chat_id: int, limit: int = 10) -> str:
    user = await user_by_chat(pool, chat_id)
    if user is None:
        return NOT_LINKED
    rows = await pool.fetch(
        """
        SELECT e.created_at, e.type, e.message, e.acked_at
          FROM events e
         ORDER BY e.created_at DESC
         LIMIT $1
        """,
        limit,
    )
    if not rows:
        return "Событий пока не было."
    lines = ["<b>Последние события</b>"]
    for row in rows:
        mark = "✅" if row["acked_at"] else "•"
        when = row["created_at"].strftime("%d.%m %H:%M")
        lines.append(f"{mark} {when} — {html.escape(row['message'])}")
    return "\n".join(lines)


async def ack_event(pool, event_id: int, chat_id: int) -> tuple[bool, str]:
    user = await user_by_chat(pool, chat_id)
    if user is None:
        return False, NOT_LINKED
    row = await pool.fetchrow(
        """
        UPDATE events SET acked_by = $2, acked_at = COALESCE(acked_at, now())
         WHERE id = $1
        RETURNING device_id, message, acked_at
        """,
        event_id,
        user["id"],
    )
    if row is None:
        return False, "Событие не найдено"
    await log_action(pool, user["id"], "ack_event", row["device_id"], {"event_id": event_id})
    who = user["name"] or user["email"]
    when = row["acked_at"].strftime("%H:%M")
    return True, f"Принято: {html.escape(who)} в {when}"


def device_link(device_id: Optional[str]) -> Optional[str]:
    url = settings.public_url.rstrip("/")
    if device_id and url.startswith("https://") and "localhost" not in url:
        return f"{url}/devices/{device_id}"
    return None
