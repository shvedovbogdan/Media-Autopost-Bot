from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def channel_controls(key: str, paused: bool = False) -> InlineKeyboardMarkup:
    """Controls for one selected channel. / Кнопки керування вибраним каналом."""
    pause_button = InlineKeyboardButton(
        text="▶️ Продовжити" if paused else "⏸ Пауза",
        callback_data=f"resume:{key}" if paused else f"pause:{key}",
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Відправити зараз", callback_data=f"send:{key}")],
            [pause_button, InlineKeyboardButton(text="📊 Оновити статус", callback_data=f"status:{key}")],
            [
                InlineKeyboardButton(text="30 хв", callback_data=f"interval:{key}:30"),
                InlineKeyboardButton(text="60 хв", callback_data=f"interval:{key}:60"),
                InlineKeyboardButton(text="180 хв", callback_data=f"interval:{key}:180"),
            ],
            [InlineKeyboardButton(text="📢 Обрати інший канал", callback_data="channels")],
        ]
    )


def channels_keyboard(channels: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, channel in channels.items():
        if not channel.get("chat_id"):
            status = "⚙️"
        elif channel.get("paused"):
            status = "⏸"
        elif channel.get("enabled", True):
            status = "✅"
        else:
            status = "⛔"
        rows.append(
            [InlineKeyboardButton(text=f"{status} {channel.get('title', key)}", callback_data=f"select:{key}")]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Каналів немає", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="🔄 Оновити", callback_data="channels")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

