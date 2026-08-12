from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from config import AUTO_START, BOT_TOKEN, LOGS_DIR, validate_environment
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
    file_handler = RotatingFileHandler(
        LOGS_DIR / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[console, file_handler], force=True)


configure_logging()
logger = logging.getLogger("media_autopost")
db = JsonDatabase()
dp = Dispatcher()
dp.include_router(admin_router)


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Головне меню"),
        BotCommand(command="channels", description="Список каналів"),
        BotCommand(command="status", description="Статус активного каналу"),
        BotCommand(command="sendnow", description="Опублікувати зараз"),
        BotCommand(command="upload", description="Додати медіа в чергу"),
        BotCommand(command="upload_stop", description="Завершити завантаження"),
        BotCommand(command="help", description="Усі команди"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    validate_environment()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler_task: asyncio.Task | None = None
    try:
        channels = db.get_channels()
        for key, channel in channels.items():
            try:
                ensure_channel_dirs(channel)
            except (OSError, ValueError) as error:
                logger.error("Cannot initialize folders for %s: %s", key, error)
        await set_commands(bot)
        await bot.delete_webhook(drop_pending_updates=False)
        if AUTO_START:
            scheduler_task = asyncio.create_task(scheduler_loop(bot), name="media-autopost-scheduler")
        logger.info("Media Autopost Bot started; channels=%s; scheduler=%s", len(channels), AUTO_START)
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

