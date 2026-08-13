from __future__ import annotations

from functools import wraps

from aiogram.types import CallbackQuery, Message
from config import OWNER_ID
from database import JsonDatabase
from services.billing import is_rental_active, rent_price_text

db = JsonDatabase()
RENTAL_FREE_COMMANDS = {"start", "help", "payments", "rentbot"}
RENTAL_FREE_CALLBACKS = ("rental", "rentplan:", "noop")


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and int(user_id) in db.get_admins())


def is_owner(user_id: int | None) -> bool:
    return bool(OWNER_ID and user_id and int(user_id) == OWNER_ID)


def has_active_rental(user_id: int | None) -> bool:
    if is_owner(user_id):
        return True
    return bool(user_id and is_rental_active(db.get_user_rental(user_id)))


def command_name(message: Message) -> str:
    text = message.text or ""
    if not text.startswith("/"):
        return ""
    return text.split(maxsplit=1)[0].split("@", 1)[0].lstrip("/").lower()


def callback_is_rental_free(callback: CallbackQuery) -> bool:
    data = callback.data or ""
    return any(data == value or data.startswith(value) for value in RENTAL_FREE_CALLBACKS)


async def answer_rental_required(message: Message) -> None:
    await message.answer(
        "⛔ Оренда бота не активна.\n\n"
        f"Ціна: <b>{rent_price_text()}</b>.\n"
        "Оплатити або продовжити доступ: <code>/rentbot</code>\n\n"
        "Owner із <code>OWNER_ID</code> користується ботом без оплати."
    )


def admin_only_message(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else None
        name = command_name(message)
        if not is_admin(user_id):
            if name not in RENTAL_FREE_COMMANDS:
                await message.answer("⛔ Немає доступу.")
                return None
            return await handler(message, *args, **kwargs)
        if name not in RENTAL_FREE_COMMANDS and not has_active_rental(user_id):
            await answer_rental_required(message)
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
        user_id = callback.from_user.id if callback.from_user else None
        if not is_admin(user_id):
            if not callback_is_rental_free(callback):
                await callback.answer("⛔ Немає доступу.", show_alert=True)
                return None
            return await handler(callback, *args, **kwargs)
        if not callback_is_rental_free(callback) and not has_active_rental(user_id):
            await callback.answer("⛔ Оренда бота не активна. Оплати /rentbot", show_alert=True)
            return None
        return await handler(callback, *args, **kwargs)

    return wrapper
