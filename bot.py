from __future__ import annotations

import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from config import AUTO_START, BOT_TOKEN, CHANNELS_DIR, LOGS_DIR, validate_environment
from database import JsonDatabase
from handlers.admin import router as admin_router
from services.publisher import scheduler_loop
from services.storage import ensure_channel_dirs


def configure_logging() -> None:
    """Console + rotating file log. / Логи в консолі та файлі з ротацією."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    handlers: list[logging.Handler] = [console]
    try:
        # Keep this separate from bot.log so Windows file locking cannot stop the bot.
        file_handler = RotatingFileHandler(
            LOGS_DIR / "runtime.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError as error:
        print(f"[WARNING] File logging is unavailable: {error}", file=sys.stderr)
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)


configure_logging()
logger = logging.getLogger("media_autopost")
db = JsonDatabase()
dp = Dispatcher()
dp.include_router(admin_router)


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Головне меню"),
        BotCommand(command="channels", description="Список каналів"),
        BotCommand(command="payments", description="Оренда бота і статус оплат"),
        BotCommand(command="rentbot", description="Оплатити або продовжити оренду"),
        BotCommand(command="addchannel", description="Додати канал"),
        BotCommand(command="status", description="Статус активного каналу"),
        BotCommand(command="checkchat", description="Перевірити доступ до каналу"),
        BotCommand(command="sendnow", description="Опублікувати зараз"),
        BotCommand(command="upload", description="Додати медіа в чергу"),
        BotCommand(command="upload_stop", description="Завершити завантаження"),
        BotCommand(command="clients", description="Owner: клієнти"),
        BotCommand(command="income", description="Owner: дохід Stars"),
        BotCommand(command="backup", description="Owner: створити бекап"),
        BotCommand(command="help", description="Усі команди"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    validate_environment()
    CHANNELS_DIR.mkdir(parents=True, exist_ok=True)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler_task: asyncio.Task | None = None
    try:
        channels = db.get_channels()
        for key, channel in channels.items():
            try:
                ensure_channel_dirs(channel)
            except (OSError, ValueError) as error:
                logger.error("Cannot initialize folders for %s: %s", key, error)
        me = await bot.get_me()
        await set_commands(bot)
        await bot.delete_webhook(drop_pending_updates=False)
        if AUTO_START:
            scheduler_task = asyncio.create_task(scheduler_loop(bot), name="media-autopost-scheduler")
        ready_lines = [
            "=" * 58,
            " BOT READY / BOT STARTED",
            "=" * 58,
            f"Telegram: @{me.username} (id={me.id})",
            f"Process PID: {os.getpid()}",
            f"Channels configured: {len(channels)}",
            f"Scheduler enabled: {AUTO_START}",
            "Open Telegram and send /start to the bot.",
            "=" * 58,
        ]
        for line in ready_lines:
            print(line, flush=True)
        logger.info(
            "Media Autopost Bot started; username=@%s; id=%s; channels=%s; scheduler=%s",
            me.username,
            me.id,
            len(channels),
            AUTO_START,
        )
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if scheduler_task and not scheduler_task.done():
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        await bot.session.close()
        logger.info("Media Autopost Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("Fatal bot error")
        raise
