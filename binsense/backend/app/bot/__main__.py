"""Telegram-бот BinSense (aiogram 3): python -m app.bot

Пул соединений с БД передаётся в обработчики через workflow data aiogram
(`dp.start_polling(bot, pool=pool)`), сама логика живёт в app/bot/service.py.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import settings
from ..db import create_pool, migrate
from . import service

log = logging.getLogger("binsense.bot")

dp = Dispatcher()

COMMANDS = [
    BotCommand(command="status", description="Сводка по системе"),
    BotCommand(command="full", description="Заполненные контейнеры и маршрут"),
    BotCommand(command="bins", description="Все контейнеры"),
    BotCommand(command="events", description="Последние события"),
    BotCommand(command="help", description="Справка"),
]


@dp.message(CommandStart(deep_link=True))
async def start_with_token(message: Message, command: CommandObject, pool) -> None:
    token = (command.args or "").strip()
    await message.answer(await service.link_account(pool, token, message.chat.id))


@dp.message(CommandStart())
async def start(message: Message, pool) -> None:
    user = await service.user_by_chat(pool, message.chat.id)
    await message.answer(service.HELP if user is not None else service.NOT_LINKED)


@dp.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(service.HELP)


@dp.message(Command("status"))
async def status_cmd(message: Message, pool) -> None:
    await message.answer(await service.status_text(pool, message.chat.id))


@dp.message(Command("full"))
async def full_cmd(message: Message, pool) -> None:
    text, urls = await service.full_text(pool, message.chat.id)
    markup = None
    if urls:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗺 Маршрут" if len(urls) == 1 else f"🗺 Маршрут {i + 1}",
                        url=url,
                    )
                ]
                for i, url in enumerate(urls)
            ]
        )
    await message.answer(text, reply_markup=markup)


@dp.message(Command("bins", "devices"))
async def bins_cmd(message: Message, pool) -> None:
    await message.answer(await service.bins_text(pool, message.chat.id))


@dp.message(Command("events"))
async def events_cmd(message: Message, pool) -> None:
    await message.answer(await service.events_text(pool, message.chat.id))


@dp.message(Command("unlink"))
async def unlink_cmd(message: Message, pool) -> None:
    await message.answer(await service.unlink(pool, message.chat.id))


@dp.callback_query(F.data.startswith("ack:"))
async def ack_callback(query: CallbackQuery, pool) -> None:
    if not query.data or query.message is None:
        return
    try:
        event_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("Некорректное событие")
        return
    ok, text = await service.ack_event(pool, event_id, query.message.chat.id)
    await query.answer(text[:190], show_alert=not ok)
    if ok:
        original = query.message.html_text if query.message.text else ""
        await query.message.edit_text(f"{original}\n✅ {text}", reply_markup=None)


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if not settings.telegram_bot_token:
        log.warning("TELEGRAM_BOT_TOKEN не задан — бот отключён (контейнер продолжит работу)")
        while True:
            await asyncio.sleep(3600)

    pool = await create_pool()
    await migrate(pool)
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    await bot.set_my_commands(COMMANDS)
    log.info("бот @%s запущен", me.username)
    try:
        await dp.start_polling(bot, pool=pool)
    finally:
        await bot.session.close()
        await pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
