from __future__ import annotations

from functools import wraps

from aiogram.types import CallbackQuery, Message
from config import OWNER_ID
from database import JsonDatabase

db = JsonDatabase()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and int(user_id) in db.get_admins())


def is_owner(user_id: int | None) -> bool:
    return bool(OWNER_ID and user_id and int(user_id) == OWNER_ID)


def admin_only_message(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if not is_admin(message.from_user.id if message.from_user else None):
            await message.answer("⛔ Немає доступу.")
            return None
        return await handler(message, *args, **kwargs)

    return wrapper


def owner_only_message(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if not is_owner(message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ця дія доступна тільки власнику бота.")
            return None
        return await handler(message, *args, **kwargs)

    return wrapper


def admin_only_callback(handler):
    @wraps(handler)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        if not is_admin(callback.from_user.id if callback.from_user else None):
            await callback.answer("⛔ Немає доступу.", show_alert=True)
            return None
        return await handler(callback, *args, **kwargs)

    return wrapper

