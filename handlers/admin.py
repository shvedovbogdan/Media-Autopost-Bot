from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from config import OWNER_ID, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS
from database import JsonDatabase
from keyboards.admin import channel_controls, channels_keyboard
from services.captions import load_caption_pack
from services.publisher import publish_channel
from services.storage import (
    ensure_channel_dirs,
    get_media_type_by_suffix,
    list_files,
    project_path,
    unique_path,
)
from utils.security import admin_only_callback, admin_only_message, owner_only_message

router = Router()
db = JsonDatabase()
upload_sessions: dict[int, str] = {}
active_channels: defaultdict[int, str] = defaultdict(str)
CHANNEL_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


def h(value: object) -> str:
    return html.escape(str(value))


def channel_paths(key: str) -> dict[str, str]:
    base = f"channels/{key}"
    return {"photos": f"{base}/photos", "videos": f"{base}/videos", "archive": f"{base}/archive"}


def queue_counts(channel: dict) -> tuple[int, int]:
    paths = channel.get("paths", {})
    photos = list_files(paths.get("photos", ""), PHOTO_EXTENSIONS)
    videos = list_files(paths.get("videos") or paths.get("video", ""), VIDEO_EXTENSIONS)
    return len(photos), len(videos)


def channel_summary(key: str, channel: dict) -> str:
    photos, videos = queue_counts(channel)
    if not channel.get("chat_id"):
        state = "⚙️ очікує chat_id"
    elif not channel.get("enabled", True):
        state = "⛔ вимкнений"
    elif channel.get("paused"):
        state = "⏸ пауза"
    else:
        state = "✅ активний"
    last_error = channel.get("last_error")
    error_line = f"\nОстання помилка: <code>{h(str(last_error)[:300])}</code>" if last_error else ""
    return (
        f"<b>{h(channel.get('title', key))}</b>\n"
        f"Ключ: <code>{h(key)}</code>\n"
        f"Канал: <code>{h(channel.get('chat_id') or 'не налаштовано')}</code>\n"
        f"Статус: <b>{state}</b>\n"
        f"Інтервал: <b>{int(channel.get('interval_minutes', 60))} хв</b>\n"
        f"Мова: <b>{h(channel.get('language', 'en'))}</b>\n"
        f"Підписи: <b>{h(channel.get('caption_pack', 'default'))}</b>\n"
        f"Черга: 📸 <b>{photos}</b> | 🎥 <b>{videos}</b>"
        f"{error_line}"
    )


def get_active_channel(user_id: int) -> tuple[str, dict | None]:
    channels = db.get_channels()
    key = active_channels[user_id]
    if key not in channels and channels:
        key = next(iter(channels))
        active_channels[user_id] = key
    return key, channels.get(key)


def command_target(message: Message, argument: str | None = None) -> str:
    """Use an explicit key or safely fall back to the first available channel."""
    if argument and argument.strip():
        return argument.strip()
    key, _ = get_active_channel(message.from_user.id)
    return key


async def show_channel(message: Message, key: str) -> None:
    channel = db.get_channel(key)
    if not channel:
        await message.answer("Канал не знайдено.")
        return
    await message.answer(channel_summary(key, channel), reply_markup=channel_controls(key, channel.get("paused", False)))


@router.message(Command("start"))
@admin_only_message
async def cmd_start(message: Message) -> None:
    key, channel = get_active_channel(message.from_user.id)
    text = (
        "<b>🎬 Media Autopost Bot</b>\n\n"
        "Один бот керує кількома незалежними каналами, чергами медіа, підписами та розкладом.\n"
        "Обери канал через /channels або відкрий /help."
    )
    await message.answer(text)
    if channel:
        await show_channel(message, key)
    else:
        await message.answer("Каналів немає. Власник може додати: /addchannel key chat_id Назва")


@router.message(Command("help"))
@admin_only_message
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>📖 Команди Media Autopost Bot</b>\n\n"
        "/channels — усі канали\n"
        "/setchannel key — обрати активний канал\n"
        "/status [key|all] — стан і черги\n"
        "/sendnow [key|all] — опублікувати зараз\n"
        "/pause [key|all] — призупинити\n"
        "/resume [key|all] — продовжити\n"
        "/interval key minutes — змінити інтервал\n"
        "/language key ua|ru|en — мова підписів\n"
        "/upload [key] — завантажувати медіа в чергу\n"
        "/upload_stop — завершити завантаження\n"
        "/stats [key] — статистика\n"
        "/archive [key] — кількість в архіві\n\n"
        "<b>Тільки власник:</b>\n"
        "/setchat key @channel|-100...\n"
        "/title key Нова назва\n"
        "/pack key default|style_1|style_2\n"
        "/footer key текст | off\n"
        "/addchannel key chat_id Назва\n"
        "/delchannel key — видаляє конфіг, але не медіа\n"
        "/addadmin user_id\n"
        "/removeadmin user_id"
    )


@router.message(Command("channels"))
@admin_only_message
async def cmd_channels(message: Message) -> None:
    channels = db.get_channels()
    if not channels:
        await message.answer(
            "<b>📢 Канали</b>\n\nКаналів ще немає. Власник може додати перший канал командою:\n"
            "<code>/addchannel key @channel Назва каналу</code>",
            reply_markup=channels_keyboard(channels),
        )
        return
    summaries = "\n\n".join(channel_summary(key, channel) for key, channel in channels.items())
    await message.answer(
        f"<b>📢 Канали</b>\n\n{summaries}",
        reply_markup=channels_keyboard(channels),
    )


@router.message(Command("setchannel"))
@admin_only_message
async def cmd_setchannel(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or parts[1].strip() not in db.get_channels():
        await message.answer("Приклад: <code>/setchannel example_channel</code>")
        return
    key = parts[1].strip()
    active_channels[message.from_user.id] = key
    await show_channel(message, key)


@router.message(Command("status"))
@admin_only_message
async def cmd_status(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    target = command_target(message, parts[1] if len(parts) == 2 else None)
    channels = db.get_channels()
    if target == "all":
        if not channels:
            await message.answer("Каналів немає.")
            return
        await message.answer("\n\n".join(channel_summary(key, channel) for key, channel in channels.items()))
        return
    await show_channel(message, target)


@router.message(Command("sendnow"))
@admin_only_message
async def cmd_sendnow(message: Message, bot: Bot) -> None:
    parts = message.text.split(maxsplit=1)
    target = command_target(message, parts[1] if len(parts) == 2 else None)
    channels = db.get_channels()
    keys = list(channels) if target == "all" else [target]
    results = []
    for key in keys:
        channel = channels.get(key)
        if not channel:
            results.append(f"{h(key)}: ⚠️ канал не знайдено")
            continue
        ok, result = await publish_channel(bot, key, channel)
        results.append(f"{h(key)}: {'✅' if ok else '⚠️'} {h(result)}")
    await message.answer("\n".join(results) if results else "Каналів немає.")


async def set_pause(message: Message, paused: bool) -> None:
    parts = message.text.split(maxsplit=1)
    target = command_target(message, parts[1] if len(parts) == 2 else None)
    channels = db.get_channels()
    if target == "all":
        for channel in channels.values():
            channel["paused"] = paused
        db.save_channels(channels)
        await message.answer("⏸ Усі канали на паузі." if paused else "▶️ Усі канали активовані.")
        return
    ok = db.update_channel(target, paused=paused)
    await message.answer(("⏸ Канал на паузі." if paused else "▶️ Канал активовано.") if ok else "Канал не знайдено.")


@router.message(Command("pause"))
@admin_only_message
async def cmd_pause(message: Message) -> None:
    await set_pause(message, True)


@router.message(Command("resume"))
@admin_only_message
async def cmd_resume(message: Message) -> None:
    await set_pause(message, False)


@router.message(Command("interval"))
@admin_only_message
async def cmd_interval(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3 or not parts[2].isdigit() or not 1 <= int(parts[2]) <= 10080:
        await message.answer("Приклад: <code>/interval example_channel 30</code> (1–10080 хв)")
        return
    ok = db.update_channel(parts[1], interval_minutes=int(parts[2]), last_attempt=None)
    await message.answer(f"✅ Інтервал: {parts[2]} хв." if ok else "Канал не знайдено.")


@router.message(Command("language"))
@admin_only_message
async def cmd_language(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3 or parts[2].lower() not in {"ua", "ru", "en"}:
        await message.answer("Приклад: <code>/language example_channel en</code>")
        return
    ok = db.update_channel(parts[1], language=parts[2].lower())
    await message.answer("✅ Мову змінено." if ok else "Канал не знайдено.")


@router.message(Command("setchat"))
@owner_only_message
async def cmd_setchat(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Приклад: <code>/setchat example_channel -1001234567890</code>")
        return
    chat_id = parts[2].strip()
    if not (chat_id.startswith("@") or (chat_id.startswith("-") and chat_id[1:].isdigit())):
        await message.answer("chat_id має бути @username або числом на кшталт -1001234567890.")
        return
    ok = db.update_channel(parts[1], chat_id=chat_id, last_error=None, last_attempt=None)
    await message.answer("✅ chat_id збережено." if ok else "Канал не знайдено.")


@router.message(Command("title"))
@owner_only_message
async def cmd_title(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3 or not parts[2].strip():
        await message.answer("Приклад: <code>/title example_channel Назва каналу</code>")
        return
    title = parts[2].strip()
    if len(title) > 100:
        await message.answer("Назва має бути не довшою за 100 символів.")
        return
    ok = db.update_channel(parts[1], title=title)
    await message.answer("✅ Назву профілю змінено." if ok else "Канал не знайдено.")


@router.message(Command("pack"))
@owner_only_message
async def cmd_pack(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3 or parts[2] not in {"default", "style_1", "style_2"}:
        await message.answer("Доступні набори: <code>default</code>, <code>style_1</code>, <code>style_2</code>.")
        return
    load_caption_pack(parts[2])
    ok = db.update_channel(parts[1], caption_pack=parts[2])
    await message.answer("✅ Набір підписів змінено." if ok else "Канал не знайдено.")


@router.message(Command("footer"))
@owner_only_message
async def cmd_footer(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Приклад: <code>/footer example_channel Текст футера</code> або <code>/footer example_channel off</code>")
        return
    footer = "" if parts[2].strip().lower() == "off" else parts[2].strip()
    if len(footer) > 350:
        await message.answer("Футер має бути не довшим за 350 символів.")
        return
    ok = db.update_channel(parts[1], caption_footer=footer)
    await message.answer("✅ Футер збережено." if ok else "Канал не знайдено.")


@router.message(Command("addchannel"))
@owner_only_message
async def cmd_addchannel(message: Message) -> None:
    parts = message.text.split(maxsplit=3)
    if len(parts) != 4 or not CHANNEL_KEY_RE.fullmatch(parts[1]):
        await message.answer("Приклад: <code>/addchannel new_channel @channel Назва каналу</code>\nКлюч: латиниця, цифри, _ або -.")
        return
    _, key, chat_id, title = parts
    if key in db.get_channels():
        await message.answer("Канал із таким ключем уже існує. Вибери інший ключ або скористайся /setchat і /title.")
        return
    if not (chat_id.startswith("@") or (chat_id.startswith("-") and chat_id[1:].isdigit())):
        await message.answer("chat_id має бути @username або числом на кшталт -1001234567890.")
        return
    channel = {
        "title": title,
        "chat_id": chat_id,
        "enabled": True,
        "paused": True,
        "language": "en",
        "interval_minutes": 180,
        "last_sent_type": None,
        "last_run": None,
        "last_attempt": None,
        "last_error": None,
        "caption_pack": "default",
        "caption_footer": "",
        "paths": channel_paths(key),
    }
    ensure_channel_dirs(channel)
    db.upsert_channel(key, channel)
    await message.answer(
        f"✅ Канал додано: <code>{h(key)}</code>\n"
        "⏸ Автопостинг на паузі. Додай медіа, перевір /sendnow і потім увімкни /resume."
    )


@router.message(Command("delchannel"))
@owner_only_message
async def cmd_delchannel(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Приклад: <code>/delchannel new_channel</code>")
        return
    ok = db.delete_channel(parts[1].strip())
    await message.answer("✅ Канал видалено з конфігу. Папки й медіа не видалялися." if ok else "Канал не знайдено.")


@router.message(Command("addadmin"))
@owner_only_message
async def cmd_addadmin(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Приклад: <code>/addadmin 123456789</code>")
        return
    db.add_admin(int(parts[1]))
    await message.answer("✅ Адміністратора додано.")


@router.message(Command("removeadmin"))
@owner_only_message
async def cmd_removeadmin(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Приклад: <code>/removeadmin 123456789</code>")
        return
    user_id = int(parts[1])
    if user_id == OWNER_ID:
        await message.answer("Власника не можна видалити.")
        return
    db.remove_admin(user_id)
    await message.answer("✅ Адміністратора видалено.")


@router.message(Command("upload"))
@admin_only_message
async def cmd_upload(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    key = command_target(message, parts[1] if len(parts) == 2 else None)
    if key not in db.get_channels():
        await message.answer("Канал не знайдено.")
        return
    upload_sessions[message.from_user.id] = key
    await message.answer(f"📥 Завантаження для <code>{h(key)}</code> увімкнено. Надсилай фото, відео або медіафайли як документи. Завершити: /upload_stop")


@router.message(Command("upload_stop"))
@admin_only_message
async def cmd_upload_stop(message: Message) -> None:
    upload_sessions.pop(message.from_user.id, None)
    await message.answer("✅ Режим завантаження вимкнено.")


@router.message(F.photo | F.video | F.document)
async def handle_media_upload(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id if message.from_user else 0
    key = upload_sessions.get(user_id)
    if not key or user_id not in db.get_admins():
        return
    channel = db.get_channel(key)
    if not channel:
        upload_sessions.pop(user_id, None)
        await message.answer("Канал не знайдено. Завантаження зупинено.")
        return
    ensure_channel_dirs(channel)
    if message.photo:
        media_type, file_obj = "photo", message.photo[-1]
        file_name = f"photo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    elif message.video:
        media_type, file_obj = "video", message.video
        file_name = message.video.file_name or f"video_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.mp4"
    else:
        file_name = message.document.file_name or "file"
        media_type = get_media_type_by_suffix(file_name)
        file_obj = message.document
        if media_type not in {"photo", "video"}:
            await message.answer(f"⚠️ Формат не підтримується: <code>{h(file_name)}</code>")
            return
    paths = channel.get("paths", {})
    folder = paths.get("photos") if media_type == "photo" else paths.get("videos") or paths.get("video")
    destination = unique_path(folder, file_name)
    await bot.download(file_obj, destination=destination)
    db.update_channel(key, last_error=None)
    await message.answer(f"✅ Додано в чергу <code>{h(key)}</code>: <code>{h(destination.name)}</code>")


@router.message(Command("stats"))
@admin_only_message
async def cmd_stats(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    key = command_target(message, parts[1] if len(parts) == 2 else None)
    if not db.get_channel(key):
        await message.answer("Канал не знайдено.")
        return
    stats = db.get_stats(key)
    now = datetime.now(timezone.utc)
    today = {"photo": 0, "video": 0}
    week = {"photo": 0, "video": 0}
    for item in stats:
        try:
            timestamp = datetime.fromisoformat(item["timestamp"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            media_type = item.get("type")
            if media_type in today and timestamp.date() == now.date():
                today[media_type] += 1
            if media_type in week and (now - timestamp).total_seconds() <= 7 * 86400:
                week[media_type] += 1
        except (KeyError, TypeError, ValueError):
            continue
    await message.answer(f"<b>📊 {h(key)}</b>\nСьогодні: 📸 {today['photo']} | 🎥 {today['video']}\n7 днів: 📸 {week['photo']} | 🎥 {week['video']}")


@router.message(Command("archive"))
@admin_only_message
async def cmd_archive(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    key = command_target(message, parts[1] if len(parts) == 2 else None)
    channel = db.get_channel(key)
    if not channel:
        await message.answer("Канал не знайдено.")
        return
    archive = project_path(channel["paths"]["archive"])
    photos = list_files(archive / "photos", PHOTO_EXTENSIONS)
    videos = list_files(archive / "videos", VIDEO_EXTENSIONS)
    videos += list_files(archive / "video", VIDEO_EXTENSIONS)
    await message.answer(f"<b>📦 Архів {h(key)}</b>\nФото: {len(photos)}\nВідео: {len(videos)}")


@router.callback_query(F.data == "channels")
@admin_only_callback
async def cb_channels(callback: CallbackQuery) -> None:
    await callback.message.edit_text("<b>📢 Обери канал</b>", reply_markup=channels_keyboard(db.get_channels()))
    await callback.answer()


@router.callback_query(F.data.startswith("select:"))
@admin_only_callback
async def cb_select(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 1)[1]
    channel = db.get_channel(key)
    if not channel:
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    active_channels[callback.from_user.id] = key
    await callback.message.edit_text(channel_summary(key, channel), reply_markup=channel_controls(key, channel.get("paused", False)))
    await callback.answer()


@router.callback_query(F.data.startswith("send:"))
@admin_only_callback
async def cb_send(callback: CallbackQuery, bot: Bot) -> None:
    key = callback.data.split(":", 1)[1]
    channel = db.get_channel(key)
    if not channel:
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    await callback.answer("Публікую…")
    ok, result = await publish_channel(bot, key, channel)
    await callback.message.answer(("✅ " if ok else "⚠️ ") + h(result))


@router.callback_query(F.data.startswith("pause:") | F.data.startswith("resume:"))
@admin_only_callback
async def cb_pause_resume(callback: CallbackQuery) -> None:
    action, key = callback.data.split(":", 1)
    paused = action == "pause"
    if not db.update_channel(key, paused=paused):
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    channel = db.get_channel(key)
    await callback.message.edit_text(channel_summary(key, channel), reply_markup=channel_controls(key, paused))
    await callback.answer("⏸ Пауза" if paused else "▶️ Активовано")


@router.callback_query(F.data.startswith("interval:"))
@admin_only_callback
async def cb_interval(callback: CallbackQuery) -> None:
    _, key, minutes = callback.data.split(":", 2)
    if not db.update_channel(key, interval_minutes=int(minutes), last_attempt=None):
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    channel = db.get_channel(key)
    await callback.message.edit_text(channel_summary(key, channel), reply_markup=channel_controls(key, channel.get("paused", False)))
    await callback.answer(f"Інтервал: {minutes} хв")


@router.callback_query(F.data.startswith("status:"))
@admin_only_callback
async def cb_status(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 1)[1]
    channel = db.get_channel(key)
    if not channel:
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    await callback.message.edit_text(channel_summary(key, channel), reply_markup=channel_controls(key, channel.get("paused", False)))
    await callback.answer("Оновлено")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
