from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError


@dataclass(frozen=True)
class ChannelCheckResult:
    ok: bool
    message: str
    normalized_chat_id: str | None = None


def is_valid_chat_ref(chat_id: str) -> bool:
    return bool(chat_id and (chat_id.startswith("@") or (chat_id.startswith("-") and chat_id[1:].isdigit())))


def explain_telegram_error(error: Exception, chat_id: object) -> str:
    text = str(error)
    lowered = text.lower()
    chat_ref = str(chat_id)

    if isinstance(error, TelegramBadRequest) and "chat not found" in lowered:
        return (
            f"Telegram не бачить канал {chat_ref}. "
            "Перевір: бот доданий у канал як адміністратор; для публічного каналу вкажи @username; "
            "для приватного каналу вкажи числовий ID виду -1001234567890."
        )
    if "not enough rights" in lowered or "need administrator rights" in lowered:
        return f"Боту не вистачає прав у каналі {chat_ref}. Дай йому права адміністратора і право публікувати."
    if isinstance(error, TelegramForbiddenError) or "bot was kicked" in lowered:
        return f"Бот не має доступу до каналу {chat_ref}. Додай його назад у канал як адміністратора."
    return f"Telegram: {type(error).__name__}: {text}"


async def check_channel_for_posting(bot: Bot, chat_id: str) -> ChannelCheckResult:
    try:
        chat = await bot.get_chat(chat_id)
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
    except TelegramAPIError as error:
        return ChannelCheckResult(False, explain_telegram_error(error, chat_id))

    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        title = chat.title or chat.username or str(chat.id)
        return ChannelCheckResult(
            False,
            f"Бот бачить канал {title}, але не є адміністратором. Додай бота в адміністратори каналу.",
            str(chat.id),
        )

    if getattr(member, "can_post_messages", True) is False:
        title = chat.title or chat.username or str(chat.id)
        return ChannelCheckResult(
            False,
            f"Бот є адміністратором каналу {title}, але без права публікувати повідомлення.",
            str(chat.id),
        )

    title = chat.title or chat.username or str(chat.id)
    return ChannelCheckResult(True, f"Канал доступний: {title} ({chat.id}). Бот має право публікувати.", str(chat.id))
