from __future__ import annotations

import asyncio
import html
import logging
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile
from config import (
    NOTIFY_OWNER,
    OWNER_ID,
    PHOTO_EXTENSIONS,
    SCHEDULER_POLL_SECONDS,
    VIDEO_EXTENSIONS,
)
from database import JsonDatabase

from services.captions import generate_caption
from services.storage import ensure_channel_dirs, list_files, project_path, unique_path
from services.telegram_checks import explain_telegram_error

logger = logging.getLogger("media_autopost.publisher")
db = JsonDatabase()
_send_lock = asyncio.Lock()


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value)
        return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
    except (TypeError, ValueError):
        return None


def due(channel: dict, now: datetime | None = None) -> bool:
    """Check whether a configured channel is ready. / Перевіряє час наступної публікації."""
    if not channel.get("enabled", True) or channel.get("paused", False) or not channel.get("chat_id"):
        return False
    reference = parse_timestamp(channel.get("last_attempt")) or parse_timestamp(channel.get("last_run"))
    if reference is None:
        return True
    interval = max(1, int(channel.get("interval_minutes", 60)))
    return ((now or datetime.now(timezone.utc)) - reference).total_seconds() >= interval * 60


def choose_media(channel: dict) -> tuple[str, Path] | None:
    paths = channel.get("paths", {})
    photos = list_files(paths.get("photos", ""), PHOTO_EXTENSIONS)
    videos = list_files(paths.get("videos") or paths.get("video", ""), VIDEO_EXTENSIONS)
    if not photos and not videos:
        return None
    if photos and videos:
        last_type = channel.get("last_sent_type")
        media_type = "video" if last_type == "photo" else "photo" if last_type == "video" else random.choice(("photo", "video"))
    else:
        media_type = "photo" if photos else "video"
    return media_type, random.choice(photos if media_type == "photo" else videos)


def update_attempt(channel_key: str, *, error: str | None = None, success_type: str | None = None) -> bool:
    """Save an attempt and return True for a changed error. / Зберігає спробу та визначає нову помилку."""
    channels = db.get_channels()
    channel = channels.get(channel_key)
    if not channel:
        return False
    previous_error = channel.get("last_error")
    now = datetime.now(timezone.utc).isoformat()
    channel["last_attempt"] = now
    channel["last_error"] = error
    if success_type:
        channel["last_run"] = now
        channel["last_sent_type"] = success_type
    db.save_channels(channels)
    return bool(error and error != previous_error)


async def publish_channel(bot: Bot, channel_key: str, channel: dict) -> tuple[bool, str]:
    """Publish one queued file and archive it. / Публікує один файл і переносить його в архів."""
    async with _send_lock:
        chat_id = channel.get("chat_id")
        if not chat_id:
            return False, "Не вказано chat_id."
        try:
            ensure_channel_dirs(channel)
            selected = choose_media(channel)
        except (OSError, ValueError) as error:
            message = f"Помилка папки медіа: {error}"
            update_attempt(channel_key, error=message)
            return False, message

        if not selected:
            message = "Черга порожня: немає фото або відео."
            update_attempt(channel_key, error=message)
            return False, message

        media_type, file_path = selected
        caption = generate_caption(
            channel_key=channel_key,
            media_type=media_type,
            lang=channel.get("language", "en"),
            footer=channel.get("caption_footer", ""),
            file_name=file_path.name,
            caption_pack=channel.get("caption_pack", "default"),
        )

        try:
            if media_type == "photo":
                await bot.send_photo(chat_id=chat_id, photo=FSInputFile(file_path), caption=caption)
                archive_folder = project_path(channel["paths"]["archive"]) / "photos"
            else:
                await bot.send_video(
                    chat_id=chat_id,
                    video=FSInputFile(file_path),
                    caption=caption,
                    supports_streaming=True,
                )
                archive_folder = project_path(channel["paths"]["archive"]) / "videos"
        except TelegramAPIError as error:
            message = explain_telegram_error(error, chat_id)
            update_attempt(channel_key, error=message)
            logger.exception("Publish error for %s", channel_key)
            return False, message
        except Exception as error:
            message = f"Помилка публікації: {type(error).__name__}: {error}"
            update_attempt(channel_key, error=message)
            logger.exception("Publish error for %s", channel_key)
            return False, message

        archive_path = unique_path(archive_folder, file_path.name)
        try:
            shutil.move(str(file_path), str(archive_path))
        except OSError as error:
            # The Telegram post succeeded, so record it even if local archiving failed.
            logger.exception("Archive error for %s", channel_key)
            update_attempt(channel_key, error=f"Опубліковано, але не перенесено в архів: {error}", success_type=media_type)
            db.add_stat(channel_key, media_type, file_path.name, caption)
            return True, f"Опубліковано {media_type}, але сталася помилка архіву: {file_path.name}"

        update_attempt(channel_key, success_type=media_type)
        db.add_stat(channel_key, media_type, file_path.name, caption)
        logger.info("Published %s to %s", file_path.name, channel_key)
        return True, f"Опубліковано {media_type}: {file_path.name}"


async def notify_owner(bot: Bot, channel_key: str, message: str) -> None:
    if not NOTIFY_OWNER or not OWNER_ID:
        return
    try:
        await bot.send_message(
            OWNER_ID,
            f"⚠️ <b>{html.escape(channel_key)}</b>\n{html.escape(message)}",
        )
    except Exception:
        logger.exception("Could not notify owner about %s", channel_key)


async def scheduler_loop(bot: Bot) -> None:
    """Run all channel schedules in one process. / Обслуговує розклад усіх каналів в одному процесі."""
    logger.info("Scheduler started")
    while True:
        channels = db.get_channels()
        for key, channel in channels.items():
            if not due(channel):
                continue
            previous_error = channel.get("last_error")
            ok, result = await publish_channel(bot, key, channel)
            if not ok:
                logger.warning("%s: %s", key, result)
                if result != previous_error:
                    await notify_owner(bot, key, result)
        await asyncio.sleep(SCHEDULER_POLL_SECONDS)
