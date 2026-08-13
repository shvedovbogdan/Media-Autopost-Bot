from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from config import (
    BOT_TOKEN,
    CAPTION_HISTORY_DIR,
    CHANNELS_DIR,
    CHANNELS_PATH,
    DATA_DIR,
    LOGS_DIR,
    OWNER_ID,
    STATS_DIR,
    validate_environment,
)
from database import JsonDatabase
from services.storage import ensure_channel_dirs


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warning(message: str) -> None:
    print(f"[УВАГА] {message}")


def error(message: str) -> None:
    print(f"[ПОМИЛКА] {message}")


def check_writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="media_bot_check_", dir=folder, delete=True):
            pass
        ok(f"Папка доступна для запису: {folder.name}")
        return True
    except OSError as exc:
        error(f"Немає доступу до папки {folder}: {exc}")
        return False


def check_local() -> tuple[JsonDatabase, int]:
    failures = 0
    validate_environment()
    ok("BOT_TOKEN і OWNER_ID мають правильний локальний формат")

    try:
        with CHANNELS_PATH.open("r", encoding="utf-8-sig") as file:
            raw_channels = json.load(file)
        if not isinstance(raw_channels, dict):
            raise ValueError("кореневе значення має бути JSON-об'єктом")
        ok("channels.json читається коректно")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        error(f"channels.json пошкоджений: {exc}")
        failures += 1

    for folder in (CHANNELS_DIR, DATA_DIR, STATS_DIR, CAPTION_HISTORY_DIR, LOGS_DIR):
        if not check_writable(folder):
            failures += 1

    database = JsonDatabase()
    for key, channel in database.get_channels().items():
        try:
            ensure_channel_dirs(channel)
            ok(f"Структура контенту каналу '{key}' готова")
        except (OSError, ValueError) as exc:
            error(f"Папки каналу '{key}' мають помилку: {exc}")
            failures += 1
    return database, failures


async def check_telegram(database: JsonDatabase) -> int:
    failures = 0
    bot = Bot(BOT_TOKEN)
    try:
        me = await bot.get_me()
        ok(f"Telegram прийняв токен: @{me.username}")

        channels = database.get_channels()
        if not channels:
            warning("Каналів ще немає. Після запуску додайте перший через /addchannel.")
            return failures

        for key, channel in channels.items():
            chat_id = channel.get("chat_id")
            if not chat_id:
                warning(f"У каналу '{key}' не вказано chat_id")
                failures += 1
                continue
            try:
                chat = await bot.get_chat(chat_id)
                member = await bot.get_chat_member(chat_id, me.id)
                if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
                    error(f"Бот не є адміністратором каналу '{key}' ({chat.title or chat_id})")
                    failures += 1
                    continue
                if getattr(member, "can_post_messages", True) is False:
                    error(f"Бот не має права публікувати в каналі '{key}'")
                    failures += 1
                    continue
                ok(f"Канал '{key}' доступний, право публікації є")
            except Exception as exc:
                error(f"Telegram-перевірка каналу '{key}' невдала: {type(exc).__name__}: {exc}")
                failures += 1
    finally:
        await bot.session.close()
    return failures


async def main() -> int:
    print("=" * 48)
    print(" Media Autopost Bot — перевірка встановлення")
    print("=" * 48)
    try:
        database, failures = check_local()
    except Exception as exc:
        error(f"Критична локальна помилка: {type(exc).__name__}: {exc}")
        return 1

    if OWNER_ID <= 0:
        error("OWNER_ID не налаштовано")
        failures += 1

    try:
        failures += await check_telegram(database)
    except Exception as exc:
        error(f"Telegram недоступний або токен неправильний: {type(exc).__name__}: {exc}")
        failures += 1

    print()
    if failures:
        error(f"Знайдено проблем: {failures}")
        return 1
    ok("Установлення справне. Бота можна запускати через start.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
