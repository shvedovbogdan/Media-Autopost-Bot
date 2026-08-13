from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from config import BOT_RENTAL_DAYS, CHANNEL_MONTHLY_STARS, CHANNEL_SUBSCRIPTION_DAYS, OWNER_ID, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS
from database import JsonDatabase
from keyboards.admin import channel_controls, channels_keyboard, main_menu_keyboard, rental_plans_keyboard
from services.billing import (
    channel_billing_status_line,
    channel_rental_user_id,
    format_paid_until,
    get_plan,
    is_rental_active,
    is_rental_banned,
    new_rental_until,
    new_paid_until,
    normalize_plan_id,
    plan_channel_limit,
    plan_price,
    plan_text,
    plan_title,
    plans_help_text,
    parse_paid_until,
    price_text,
    renewed_rental_until_for_plan,
    renewed_rental_until,
    renewed_paid_until,
    rent_price_text,
    rental_channel_limit,
    rental_plan_id,
    rental_status_text,
)
from services.backups import create_backup
from services.captions import load_caption_pack
from services.publisher import publish_channel
from services.storage import (
    ensure_channel_dirs,
    get_media_type_by_suffix,
    list_files,
    project_path,
    unique_path,
)
from services.telegram_checks import check_channel_for_posting, is_valid_chat_ref
from utils.security import admin_only_callback, admin_only_message, answer_rental_required, has_active_rental, owner_only_message

router = Router()
db = JsonDatabase()
upload_sessions: dict[int, str] = {}
active_channels: defaultdict[int, str] = defaultdict(str)
CHANNEL_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


def h(value: object) -> str:
    return html.escape(str(value))


async def safe_edit_text(message: Message, text: str, **kwargs) -> bool:
    try:
        await message.edit_text(text, **kwargs)
        return True
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            return False
        raise


def channel_paths(key: str) -> dict[str, str]:
    base = f"channels/{key}"
    return {"photos": f"{base}/photos", "videos": f"{base}/videos", "archive": f"{base}/archive"}


def build_channel_config(
    *,
    key: str,
    title: str,
    chat_id: str,
    created_by: int,
    payment_required: bool,
    paid_until: str | None = None,
) -> dict:
    return {
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
        "created_by": created_by,
        "payment_required": payment_required,
        "billing_exempt": created_by == OWNER_ID,
        "billing_user_id": created_by,
        "rental_user_id": created_by,
        "paid_until": paid_until,
        "stars_per_period": CHANNEL_MONTHLY_STARS if payment_required else 0,
        "subscription_days": CHANNEL_SUBSCRIPTION_DAYS if payment_required else 0,
    }


async def send_stars_invoice(
    message: Message,
    *,
    payload: str,
    key: str,
    title: str,
    invoice_title: str,
    amount: int,
    days: int,
) -> None:
    invoice_description = (
        f"Профіль: {key}\n"
        f"Меню: {title[:70]}\n"
        f"Термін: {days} днів\n"
        "Оплата активує або продовжить доступ."
    )[:255]
    await message.answer_invoice(
        title=invoice_title,
        description=invoice_description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{amount} Stars / {days} днів", amount=amount)],
    )


async def send_bot_rental_invoice(message: Message, *, payload: str, plan_id: str) -> None:
    plan = get_plan(plan_id)
    await send_stars_invoice(
        message,
        payload=payload,
        key=f"BOT_RENTAL_{plan['title']}",
        title=f"Оренда Media Autopost Bot — {plan['title']}",
        invoice_title=f"Оренда {plan['title']}",
        amount=int(plan["stars"]),
        days=int(plan["days"]),
    )


def addchannel_help_text() -> str:
    return (
        "<b>Як додати канал</b>\n\n"
        "Формат:\n"
        "<code>/addchannel key chat_id Назва для меню</code>\n\n"
        "<b>Що означає кожне поле:</b>\n"
        "1. <code>key</code> — внутрішній ключ профілю. Це також назва папки з контентом.\n"
        "   Це не @username каналу і не назва каналу в Telegram.\n"
        "2. <code>chat_id</code> — куди бот буде публікувати. Для публічного каналу: <code>@channel</code>. "
        "Для приватного: ID виду <code>-1001234567890</code>.\n"
        "3. <code>Назва для меню</code> — як канал буде показуватись у меню бота.\n\n"
        "<b>Приклад:</b>\n"
        "<code>/addchannel HOTBOYS_YAOI_NS @HOT_BOYSES HOTBOYS + YAOI NS</code>\n\n"
        "Після успішного додавання бот створить папки:\n"
        "<code>channels/HOTBOYS_YAOI_NS/photos</code>\n"
        "<code>channels/HOTBOYS_YAOI_NS/videos</code>\n"
        "<code>channels/HOTBOYS_YAOI_NS/archive</code>\n\n"
        f"<b>Оплата:</b>\n"
        f"Owner користується ботом без оплати.\n"
        f"Клієнти мають оплатити оренду бота: <b>{price_text()}</b> через Telegram Stars.\n"
        f"Оплатити або продовжити: <code>/rentbot</code>\n\n"
        "Правила для <code>key</code>: тільки латиниця, цифри, <code>_</code> або <code>-</code>, без пробілів."
    )


def key_help_line() -> str:
    return (
        "<b>Що таке key?</b>\n"
        "<code>key</code> — це коротка внутрішня назва профілю і папки, наприклад "
        "<code>HOTBOYS_YAOI_NS</code>. Він створюється командою <code>/addchannel</code> "
        "і потім використовується в командах <code>/upload</code>, <code>/sendnow</code>, "
        "<code>/pause</code>, <code>/resume</code>, <code>/checkchat</code>."
    )


def queue_counts(channel: dict) -> tuple[int, int]:
    paths = channel.get("paths", {})
    photos = list_files(paths.get("photos", ""), PHOTO_EXTENSIONS)
    videos = list_files(paths.get("videos") or paths.get("video", ""), VIDEO_EXTENSIONS)
    return len(photos), len(videos)


def channel_summary(key: str, channel: dict) -> str:
    photos, videos = queue_counts(channel)
    rental = db.get_user_rental(channel_rental_user_id(channel))
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
        f"Ключ/папка: <code>{h(key)}</code>\n"
        f"Telegram-канал: <code>{h(channel.get('chat_id') or 'не налаштовано')}</code>\n"
        f"Статус: <b>{state}</b>\n"
        f"Інтервал: <b>{int(channel.get('interval_minutes', 60))} хв</b>\n"
        f"Мова: <b>{h(channel.get('language', 'en'))}</b>\n"
        f"Підписи: <b>{h(channel.get('caption_pack', 'default'))}</b>\n"
        f"{channel_billing_status_line(channel, rental, key)}\n"
        f"Черга: 📸 <b>{photos}</b> | 🎥 <b>{videos}</b>"
        f"{error_line}"
    )


def visible_channels(user_id: int) -> dict[str, dict]:
    channels = db.get_channels()
    if user_id == OWNER_ID:
        return channels
    return {key: channel for key, channel in channels.items() if channel_rental_user_id(channel) == user_id}


def can_access_channel(user_id: int, key: str, channel: dict | None = None) -> bool:
    if user_id == OWNER_ID:
        return True
    channel = channel or db.get_channel(key)
    return bool(channel and channel_rental_user_id(channel) == user_id)


def get_active_channel(user_id: int) -> tuple[str, dict | None]:
    channels = visible_channels(user_id)
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


def user_channel_keys(user_id: int) -> list[str]:
    return [
        key
        for key, channel in db.get_channels().items()
        if channel_rental_user_id(channel) == user_id
    ]


def user_channel_limit_text(user_id: int, rental: dict | None) -> str:
    if user_id == OWNER_ID:
        return "Ліміт каналів: <b>без обмежень для owner</b>"
    limit = rental_channel_limit(rental)
    used = len(user_channel_keys(user_id))
    return f"Ліміт каналів: <b>{used}/{limit}</b>"


def format_client_line(user_id: int, rental: dict | None) -> str:
    channels_count = len(user_channel_keys(user_id))
    if user_id == OWNER_ID:
        return f"• <code>{user_id}</code> — owner, каналів: <b>{channels_count}</b>"
    if not rental:
        return f"• <code>{user_id}</code> — без оренди, каналів: <b>{channels_count}</b>"
    plan_id = rental_plan_id(rental)
    banned = " ⛔ banned" if is_rental_banned(rental) else ""
    active = "✅" if is_rental_active(rental) else "⚠️"
    return (
        f"• <code>{user_id}</code> — {active} <b>{h(plan_title(plan_id))}</b>, "
        f"до <b>{h(format_paid_until(rental.get('paid_until')))}</b>, "
        f"каналів: <b>{channels_count}/{plan_channel_limit(plan_id)}</b>{banned}"
    )


def client_details_text(user_id: int) -> str:
    rental = db.get_user_rental(user_id)
    channels = user_channel_keys(user_id)
    payments = [
        payment
        for payment in db.get_payments().values()
        if int(payment.get("user_id", 0) or 0) == user_id and payment.get("status") == "paid"
    ]
    paid_total = sum(int(payment.get("amount", 0) or 0) for payment in payments)
    lines = [
        f"<b>Клієнт <code>{user_id}</code></b>",
        rental_status_text(user_id, rental),
        user_channel_limit_text(user_id, rental),
        f"Каналів: <b>{len(channels)}</b>",
        f"Оплат: <b>{len(payments)}</b>",
        f"Сума оплат: <b>{paid_total} Stars</b>",
    ]
    if rental and rental.get("banned"):
        lines.append(f"Блокування: <b>{h(rental.get('ban_reason') or 'без причини')}</b>")
    if channels:
        lines.append("\n<b>Канали:</b>")
        lines.extend(f"• <code>{h(key)}</code>" for key in channels)
    return "\n".join(lines)


async def show_channel(message: Message, key: str) -> None:
    channel = db.get_channel(key)
    user_id = message.from_user.id if message.from_user else 0
    if not channel or not can_access_channel(user_id, key, channel):
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
    await message.answer(text, reply_markup=main_menu_keyboard())
    if channel:
        await show_channel(message, key)
    else:
        await message.answer("Каналів ще немає.\n\n" + addchannel_help_text())


@router.message(Command("help"))
@admin_only_message
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>📖 Команди Media Autopost Bot</b>\n\n"
        f"{key_help_line()}\n\n"
        "<b>Три головні поля:</b>\n"
        "<code>key</code> — назва профілю і папки з контентом.\n"
        "<code>chat_id</code> — @username або -100... цільового Telegram-каналу.\n"
        "<code>Назва</code> — текст, який видно в меню бота.\n\n"
        "<b>Створення каналу:</b>\n"
        "<code>/addchannel HOTBOYS_YAOI_NS @HOT_BOYSES HOTBOYS + YAOI NS</code>\n\n"
        f"Owner користується ботом без оплати. Для клієнтів оренда бота: <b>{price_text()}</b> через Stars.\n\n"
        "/channels — усі канали\n"
        "/payments — ціна та статус оренди\n"
        "/rentbot — оплатити або продовжити оренду бота\n"
        "/addchannel key chat_id Назва для меню — додати новий профіль\n"
        "/setchannel key — обрати активний канал\n"
        "/status [key|all] — стан і черги\n"
        "/checkchat [key] — перевірити доступ бота до каналу\n"
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
        "/clients — список клієнтів\n"
        "/client user_id — картка клієнта\n"
        "/extend user_id days [basic|pro|vip] — продовжити доступ\n"
        "/trial user_id days [basic|pro|vip] — видати тестовий період\n"
        "/ban user_id [причина] — заблокувати клієнта\n"
        "/unban user_id — розблокувати\n"
        "/income — дохід у Stars\n"
        "/payments_history [limit] — історія оплат\n"
        "/backup — створити резервну копію зараз\n"
        "/setchat key @channel|-100...\n"
        "/title key Нова назва\n"
        "/pack key default|style_1|style_2\n"
        "/footer key текст | off\n"
        "/delchannel key — видаляє конфіг, але не медіа\n"
        "/addadmin user_id\n"
        "/removeadmin user_id"
    )


@router.message(Command("channels"))
@admin_only_message
async def cmd_channels(message: Message) -> None:
    channels = visible_channels(message.from_user.id if message.from_user else 0)
    if not channels:
        await message.answer(
            "<b>📢 Канали</b>\n\nКаналів ще немає.\n\n" + addchannel_help_text(),
            reply_markup=channels_keyboard(channels),
        )
        return
    summaries = "\n\n".join(channel_summary(key, channel) for key, channel in channels.items())
    await message.answer(
        f"<b>📢 Канали</b>\n\n{summaries}",
        reply_markup=channels_keyboard(channels),
    )


@router.message(Command("payments"))
@admin_only_message
async def cmd_payments(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    rental = db.get_user_rental(user_id)
    channels = visible_channels(user_id)
    lines = [
        "<b>⭐ Оренда бота</b>",
        "",
        "<b>Тарифи:</b>",
        plans_help_text(),
        "",
        "Owner із OWNER_ID користується ботом без оплати.",
        rental_status_text(user_id, rental),
        user_channel_limit_text(user_id, rental),
        "",
        "Оплатити або продовжити: <code>/rentbot basic</code>, <code>/rentbot pro</code> або <code>/rentbot vip</code>",
        "",
        "<b>Канали:</b>",
    ]
    if not channels:
        lines.append("Каналів ще немає.")
    else:
        for key, channel in channels.items():
            channel_rental = db.get_user_rental(channel_rental_user_id(channel))
            lines.append(f"• <code>{h(key)}</code> — {channel_billing_status_line(channel, channel_rental, key)}")
    lines.extend(
        [
            "",
            "Додати канал:",
            "<code>/addchannel key @channel Назва для меню</code>",
        ]
    )
    await message.answer("\n".join(lines), reply_markup=rental_plans_keyboard())


@router.message(Command("rentbot"))
@admin_only_message
async def cmd_rentbot(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if user_id == OWNER_ID:
        await message.answer("✅ Для owner оренда бота не потрібна. Доступ без обмежень.")
        return
    rental = db.get_user_rental(user_id)
    if is_rental_banned(rental):
        await message.answer("⛔ Ти заблокований owner. Оплата оренди недоступна.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) == 1:
        await message.answer(
            "<b>⭐ Обери тариф оренди</b>\n\n"
            f"{plans_help_text()}\n\n"
            "Приклади:\n"
            "<code>/rentbot basic</code>\n"
            "<code>/rentbot pro</code>\n"
            "<code>/rentbot vip</code>",
            reply_markup=rental_plans_keyboard(),
        )
        return
    plan_id = normalize_plan_id(parts[1])
    plan = get_plan(plan_id)
    payload = f"rent_bot:{uuid4().hex}"
    db.upsert_payment(
        payload,
        {
            "status": "pending",
            "kind": "rent_bot",
            "user_id": user_id,
            "plan": plan_id,
            "amount": int(plan["stars"]),
            "currency": "XTR",
            "rental_days": int(plan["days"]),
            "channel_limit": int(plan["channel_limit"]),
            "current_paid_until": rental.get("paid_until") if rental else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await message.answer(
        f"⭐ Оренда Media Autopost Bot: <b>{h(plan_text(plan_id))}</b>.\n"
        f"Поточний статус: {rental_status_text(user_id, rental)}\n\n"
        "Після оплати доступ активується автоматично."
    )
    await send_bot_rental_invoice(message, payload=payload, plan_id=plan_id)


@router.message(Command("setchannel"))
@admin_only_message
async def cmd_setchannel(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    user_id = message.from_user.id if message.from_user else 0
    if len(parts) != 2 or parts[1].strip() not in visible_channels(user_id):
        await message.answer(
            "Приклад: <code>/setchannel HOTBOYS_YAOI_NS</code>\n"
            "Тут <code>HOTBOYS_YAOI_NS</code> — це <code>key</code>, створений командою <code>/addchannel</code>."
        )
        return
    key = parts[1].strip()
    active_channels[user_id] = key
    await show_channel(message, key)


@router.message(Command("status"))
@admin_only_message
async def cmd_status(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    target = command_target(message, parts[1] if len(parts) == 2 else None)
    channels = db.get_channels()
    if target == "all":
        channels = visible_channels(message.from_user.id if message.from_user else 0)
        if not channels:
            await message.answer("Каналів немає.")
            return
        await message.answer("\n\n".join(channel_summary(key, channel) for key, channel in channels.items()))
        return
    await show_channel(message, target)


@router.message(Command("checkchat"))
@admin_only_message
async def cmd_checkchat(message: Message, bot: Bot) -> None:
    parts = message.text.split(maxsplit=1)
    key = command_target(message, parts[1] if len(parts) == 2 else None)
    channel = db.get_channel(key)
    if not channel or not can_access_channel(message.from_user.id if message.from_user else 0, key, channel):
        await message.answer("Канал не знайдено.")
        return
    chat_id = channel.get("chat_id")
    if not chat_id:
        await message.answer(
            "У цього профілю ще не вказано <code>chat_id</code>.\n"
            "Приклад: <code>/setchat HOTBOYS_YAOI_NS @HOT_BOYSES</code>\n"
            "<code>key</code> лишається назвою папки, а <code>@HOT_BOYSES</code> — це Telegram-канал."
        )
        return
    result = await check_channel_for_posting(bot, chat_id)
    if result.ok and result.normalized_chat_id and result.normalized_chat_id != str(chat_id):
        db.update_channel(key, chat_id=result.normalized_chat_id, last_error=None)
        await message.answer(f"✅ {h(result.message)}\nЗбережено точний ID: <code>{h(result.normalized_chat_id)}</code>")
        return
    await message.answer(("✅ " if result.ok else "⚠️ ") + h(result.message))


@router.message(Command("sendnow"))
@admin_only_message
async def cmd_sendnow(message: Message, bot: Bot) -> None:
    parts = message.text.split(maxsplit=1)
    target = command_target(message, parts[1] if len(parts) == 2 else None)
    user_id = message.from_user.id if message.from_user else 0
    channels = visible_channels(user_id)
    keys = list(channels) if target == "all" else [target]
    results = []
    for key in keys:
        channel = db.get_channel(key)
        if not can_access_channel(user_id, key, channel):
            channel = None
        if not channel:
            results.append(f"{h(key)}: ⚠️ канал не знайдено")
            continue
        ok, result = await publish_channel(bot, key, channel)
        results.append(f"{h(key)}: {'✅' if ok else '⚠️'} {h(result)}")
    await message.answer("\n".join(results) if results else "Каналів немає.")


async def set_pause(message: Message, paused: bool) -> None:
    parts = message.text.split(maxsplit=1)
    target = command_target(message, parts[1] if len(parts) == 2 else None)
    user_id = message.from_user.id if message.from_user else 0
    channels = visible_channels(user_id)
    if target == "all":
        all_channels = db.get_channels()
        for channel in channels.values():
            channel["paused"] = paused
        for key, channel in channels.items():
            all_channels[key] = channel
        db.save_channels(all_channels)
        await message.answer("⏸ Усі канали на паузі." if paused else "▶️ Усі канали активовані.")
        return
    if not can_access_channel(user_id, target):
        await message.answer("Канал не знайдено.")
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
        await message.answer("Приклад: <code>/interval HOTBOYS_YAOI_NS 30</code> (1–10080 хв)")
        return
    if not can_access_channel(message.from_user.id if message.from_user else 0, parts[1]):
        await message.answer("Канал не знайдено.")
        return
    ok = db.update_channel(parts[1], interval_minutes=int(parts[2]), last_attempt=None)
    await message.answer(f"✅ Інтервал: {parts[2]} хв." if ok else "Канал не знайдено.")


@router.message(Command("language"))
@admin_only_message
async def cmd_language(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3 or parts[2].lower() not in {"ua", "ru", "en"}:
        await message.answer("Приклад: <code>/language HOTBOYS_YAOI_NS en</code>")
        return
    if not can_access_channel(message.from_user.id if message.from_user else 0, parts[1]):
        await message.answer("Канал не знайдено.")
        return
    ok = db.update_channel(parts[1], language=parts[2].lower())
    await message.answer("✅ Мову змінено." if ok else "Канал не знайдено.")


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot) -> None:
    payload = pre_checkout_query.invoice_payload
    payment = db.get_payment(payload)
    if not payment:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Рахунок не знайдено або він застарів. Створи новий рахунок командою бота.",
        )
        return
    if payment.get("status") != "pending":
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Цей рахунок уже оброблено. Створи новий рахунок командою бота.",
        )
        return
    if int(payment.get("user_id", 0)) != pre_checkout_query.from_user.id:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Цей рахунок створений для іншого користувача.",
        )
        return
    if pre_checkout_query.currency != payment.get("currency") or int(payment.get("amount", 0)) != pre_checkout_query.total_amount:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Сума рахунку змінилась. Створи новий рахунок командою бота.",
        )
        return
    if payment.get("kind") == "rent_bot" and is_rental_banned(db.get_user_rental(pre_checkout_query.from_user.id)):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Оплата недоступна, бо owner заблокував цей доступ.",
        )
        return
    if payment.get("kind") == "add_channel" and db.get_channel(str(payment.get("key", ""))):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Профіль із таким key уже існує. Створи інший key.",
        )
        return
    if payment.get("kind") == "renew_channel" and not db.get_channel(str(payment.get("key", ""))):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Канал для продовження не знайдено.",
        )
        return
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(Command("setchat"))
@owner_only_message
async def cmd_setchat(message: Message, bot: Bot) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer(
            "Формат: <code>/setchat key chat_id</code>\n\n"
            "<code>key</code> — профіль/папка, створений через <code>/addchannel</code>.\n"
            "<code>chat_id</code> — новий Telegram-канал для публікації.\n\n"
            "Приклад для публічного каналу:\n"
            "<code>/setchat HOTBOYS_YAOI_NS @HOT_BOYSES</code>\n\n"
            "Приклад для приватного каналу:\n"
            "<code>/setchat HOTBOYS_YAOI_NS -1001234567890</code>"
        )
        return
    chat_id = parts[2].strip()
    if not is_valid_chat_ref(chat_id):
        await message.answer("<code>chat_id</code> має бути <code>@username</code> або числом на кшталт <code>-1001234567890</code>.")
        return
    if not db.get_channel(parts[1]):
        await message.answer("Канал не знайдено.")
        return
    result = await check_channel_for_posting(bot, chat_id)
    if not result.ok:
        await message.answer("⚠️ chat_id не збережено.\n" + h(result.message))
        return
    saved_chat_id = result.normalized_chat_id or chat_id
    db.update_channel(parts[1], chat_id=saved_chat_id, last_error=None, last_attempt=None)
    await message.answer(f"✅ chat_id збережено: <code>{h(saved_chat_id)}</code>\n{h(result.message)}")


@router.message(Command("title"))
@owner_only_message
async def cmd_title(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3 or not parts[2].strip():
        await message.answer(
            "Формат: <code>/title key Назва для меню</code>\n"
            "Це змінює тільки назву в меню бота, а не папку і не Telegram-канал.\n\n"
            "Приклад: <code>/title HOTBOYS_YAOI_NS HOTBOYS + YAOI NS</code>"
        )
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
        await message.answer(
            "Формат: <code>/pack key default|style_1|style_2</code>\n"
            "Приклад: <code>/pack HOTBOYS_YAOI_NS style_1</code>"
        )
        return
    load_caption_pack(parts[2])
    ok = db.update_channel(parts[1], caption_pack=parts[2])
    await message.answer("✅ Набір підписів змінено." if ok else "Канал не знайдено.")


@router.message(Command("footer"))
@owner_only_message
async def cmd_footer(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Приклад: <code>/footer HOTBOYS_YAOI_NS Текст футера</code>\n"
            "Вимкнути футер: <code>/footer HOTBOYS_YAOI_NS off</code>"
        )
        return
    footer = "" if parts[2].strip().lower() == "off" else parts[2].strip()
    if len(footer) > 350:
        await message.answer("Футер має бути не довшим за 350 символів.")
        return
    ok = db.update_channel(parts[1], caption_footer=footer)
    await message.answer("✅ Футер збережено." if ok else "Канал не знайдено.")


@router.message(Command("addchannel"))
@admin_only_message
async def cmd_addchannel(message: Message, bot: Bot) -> None:
    parts = message.text.split(maxsplit=3)
    if len(parts) != 4 or not CHANNEL_KEY_RE.fullmatch(parts[1]):
        await message.answer(addchannel_help_text())
        return
    _, key, chat_id, title = parts
    user_id = message.from_user.id if message.from_user else 0
    if key in db.get_channels():
        await message.answer(
            "Профіль із таким <code>key</code> уже існує.\n\n"
            "Якщо треба змінити Telegram-канал:\n"
            f"<code>/setchat {h(key)} @HOT_NEW_CHANNEL</code>\n\n"
            "Якщо треба змінити назву в меню:\n"
            f"<code>/title {h(key)} Нова назва</code>\n\n"
            "Якщо це інший канал, створи інший <code>key</code>."
        )
        return
    rental = db.get_user_rental(user_id)
    if user_id != OWNER_ID:
        limit = rental_channel_limit(rental)
        used = len(user_channel_keys(user_id))
        if used >= limit:
            await message.answer(
                f"⛔ Ліміт каналів за твоїм тарифом вичерпано: <b>{used}/{limit}</b>.\n\n"
                "Щоб додати більше каналів, перейди на вищий тариф:\n"
                "<code>/rentbot pro</code> або <code>/rentbot vip</code>"
            )
            return
    if not is_valid_chat_ref(chat_id):
        await message.answer("<code>chat_id</code> має бути <code>@username</code> або числом на кшталт <code>-1001234567890</code>.")
        return
    result = await check_channel_for_posting(bot, chat_id)
    if not result.ok:
        await message.answer("⚠️ Канал не додано.\n" + h(result.message))
        return
    saved_chat_id = result.normalized_chat_id or chat_id

    channel = build_channel_config(
        key=key,
        title=title,
        chat_id=saved_chat_id,
        created_by=user_id,
        payment_required=False,
    )
    ensure_channel_dirs(channel)
    db.upsert_channel(key, channel)
    await message.answer(
        f"✅ Канал додано: <code>{h(key)}</code>\n"
        f"Назва в меню: <b>{h(title)}</b>\n"
        f"Папка контенту: <code>channels/{h(key)}</code>\n"
        f"Telegram: {h(result.message)}\n"
        f"{channel_billing_status_line(channel, db.get_user_rental(channel_rental_user_id(channel)), key)}\n"
        "⏸ Автопостинг на паузі.\n\n"
        "Далі:\n"
        f"1. Додай медіа: <code>/upload {h(key)}</code>\n"
        f"2. Перевір канал: <code>/checkchat {h(key)}</code>\n"
        f"3. Тестова публікація: <code>/sendnow {h(key)}</code>\n"
        f"4. Увімкни розклад: <code>/resume {h(key)}</code>"
    )


@router.message(Command("renewchannel"))
@admin_only_message
async def cmd_renewchannel(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "Формат: <code>/renewchannel key</code>\n"
            "Приклад: <code>/renewchannel HOTBOYS_YAOI_NS</code>"
        )
        return
    key = parts[1].strip()
    channel = db.get_channel(key)
    if not channel:
        await message.answer("Канал не знайдено.")
        return
    if not channel.get("payment_required", False):
        await message.answer("Для цього каналу оплата не потрібна, бо він доданий owner.")
        return
    user_id = message.from_user.id if message.from_user else 0
    payload = f"renew_channel:{uuid4().hex}"
    db.upsert_payment(
        payload,
        {
            "status": "pending",
            "kind": "renew_channel",
            "user_id": user_id,
            "key": key,
            "title": channel.get("title", key),
            "chat_id": channel.get("chat_id"),
            "amount": CHANNEL_MONTHLY_STARS,
            "currency": "XTR",
            "subscription_days": CHANNEL_SUBSCRIPTION_DAYS,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await message.answer(
        f"⭐ Продовження каналу <code>{h(key)}</code>: <b>{price_text()}</b>.\n"
        f"Поточна дата оплати: <b>{h(format_paid_until(channel.get('paid_until')))}</b>."
    )
    await send_stars_invoice(
        message,
        payload=payload,
        key=key,
        title=str(channel.get("title", key)),
        invoice_title="Продовження каналу",
        amount=CHANNEL_MONTHLY_STARS,
        days=CHANNEL_SUBSCRIPTION_DAYS,
    )


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, bot: Bot) -> None:
    payment = message.successful_payment
    if not payment:
        return
    payload = payment.invoice_payload
    record = db.get_payment(payload)
    if not record:
        await message.answer(
            "✅ Оплату отримано, але бот не знайшов локальний рахунок.\n"
            "Напиши owner, щоб він перевірив <code>data/channel_payments.json</code>."
        )
        return
    if record.get("status") == "paid":
        await message.answer("✅ Ця оплата вже була оброблена.")
        return
    if payment.currency != record.get("currency") or payment.total_amount < int(record.get("amount", 0)):
        db.update_payment(
            payload,
            status="amount_mismatch",
            paid_at=datetime.now(timezone.utc).isoformat(),
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )
        await message.answer("⚠️ Оплату отримано, але сума не збігається з рахунком. Напиши owner.")
        return

    kind = record.get("kind")
    key = str(record.get("key", "")).strip()
    if kind == "rent_bot":
        user_id = int(record.get("user_id", 0))
        current_rental = db.get_user_rental(user_id)
        plan_id = normalize_plan_id(record.get("plan"))
        plan = get_plan(plan_id)
        paid_until = renewed_rental_until_for_plan(current_rental.get("paid_until") if current_rental else None, plan_id)
        total_paid = int((current_rental or {}).get("total_paid_stars", 0)) + int(payment.total_amount)
        payments_count = int((current_rental or {}).get("payments_count", 0)) + 1
        db.add_admin(user_id)
        db.upsert_user_rental(
            user_id,
            {
                "user_id": user_id,
                "plan": plan_id,
                "plan_title": plan["title"],
                "channel_limit": int(plan["channel_limit"]),
                "paid_until": paid_until,
                "last_paid_at": datetime.now(timezone.utc).isoformat(),
                "last_amount": payment.total_amount,
                "total_paid_stars": total_paid,
                "payments_count": payments_count,
                "currency": payment.currency,
                "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                "banned": False,
                "reminders_sent": [],
            },
        )
        db.update_payment(
            payload,
            status="paid",
            paid_at=datetime.now(timezone.utc).isoformat(),
            plan=plan_id,
            paid_until=paid_until,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )
        await message.answer(
            f"✅ Оренду бота оплачено: <b>{h(payment.total_amount)} Stars</b>.\n"
            f"Тариф: <b>{h(plan_title(plan_id))}</b>\n"
            f"Доступ активний до: <b>{h(format_paid_until(paid_until))}</b>\n\n"
            "Тепер можна користуватися ботом і додавати канали:\n"
            "<code>/addchannel key @channel Назва для меню</code>"
        )
        try:
            await bot.send_message(
                OWNER_ID,
                f"⭐ Оплата Stars отримана.\n"
                f"Тип: оренда бота\n"
                f"Тариф: <b>{h(plan_title(plan_id))}</b>\n"
                f"Сума: <b>{h(payment.total_amount)} XTR</b>\n"
                f"Користувач: <code>{h(user_id)}</code>\n"
                f"Доступ до: <b>{h(format_paid_until(paid_until))}</b>",
            )
        except Exception:
            pass
        return

    if kind == "add_channel":
        if db.get_channel(key):
            db.update_payment(
                payload,
                status="paid_duplicate_key",
                paid_at=datetime.now(timezone.utc).isoformat(),
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            await message.answer("⚠️ Оплату отримано, але профіль із таким key уже існує. Напиши owner.")
            return
        paid_until = new_paid_until()
        channel = build_channel_config(
            key=key,
            title=str(record.get("title", key)),
            chat_id=str(record.get("chat_id", "")),
            created_by=int(record.get("user_id", 0)),
            payment_required=True,
            paid_until=paid_until,
        )
        ensure_channel_dirs(channel)
        db.upsert_channel(key, channel)
        db.update_payment(
            payload,
            status="paid",
            paid_at=datetime.now(timezone.utc).isoformat(),
            paid_until=paid_until,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )
        await message.answer(
            f"✅ Оплату отримано: <b>{h(payment.total_amount)} Stars</b>.\n"
            f"Канал створено: <code>{h(key)}</code>\n"
            f"Оплачено до: <b>{h(format_paid_until(paid_until))}</b>\n"
            f"Папка контенту: <code>channels/{h(key)}</code>\n\n"
            "Далі:\n"
            f"1. <code>/upload {h(key)}</code>\n"
            f"2. <code>/checkchat {h(key)}</code>\n"
            f"3. <code>/sendnow {h(key)}</code>\n"
            f"4. <code>/resume {h(key)}</code>"
        )
        try:
            await bot.send_message(
                OWNER_ID,
                f"⭐ Оплата Stars отримана.\n"
                f"Тип: legacy +1 канал\n"
                f"Канал: <code>{h(key)}</code>\n"
                f"Сума: <b>{h(payment.total_amount)} XTR</b>\n"
                f"Користувач: <code>{h(record.get('user_id'))}</code>",
            )
        except Exception:
            pass
        return

    if kind == "renew_channel":
        channel = db.get_channel(key)
        if not channel:
            db.update_payment(
                payload,
                status="paid_missing_channel",
                paid_at=datetime.now(timezone.utc).isoformat(),
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            await message.answer("⚠️ Оплату отримано, але канал для продовження не знайдено. Напиши owner.")
            return
        paid_until = renewed_paid_until(channel.get("paid_until"))
        db.update_channel(key, paid_until=paid_until, last_error=None)
        db.update_payment(
            payload,
            status="paid",
            paid_at=datetime.now(timezone.utc).isoformat(),
            paid_until=paid_until,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )
        await message.answer(
            f"✅ Канал продовжено: <code>{h(key)}</code>\n"
            f"Оплачено до: <b>{h(format_paid_until(paid_until))}</b>\n"
            f"Сума: <b>{h(payment.total_amount)} Stars</b>"
        )
        try:
            await bot.send_message(
                OWNER_ID,
                f"⭐ Оплата Stars отримана.\n"
                f"Тип: продовження\n"
                f"Канал: <code>{h(key)}</code>\n"
                f"Сума: <b>{h(payment.total_amount)} XTR</b>\n"
                f"Користувач: <code>{h(record.get('user_id'))}</code>",
            )
        except Exception:
            pass
        return

    db.update_payment(payload, status="paid_unknown_kind", paid_at=datetime.now(timezone.utc).isoformat())
    await message.answer("✅ Оплату отримано, але тип рахунку невідомий. Напиши owner.")


@router.message(Command("delchannel"))
@owner_only_message
async def cmd_delchannel(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Приклад: <code>/delchannel HOTBOYS_YAOI_NS</code>")
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


@router.message(Command("clients"))
@owner_only_message
async def cmd_clients(message: Message) -> None:
    rentals = db.get_bot_rentals()
    admins = db.get_admins()
    user_ids = set(int(user_id) for user_id in rentals if str(user_id).isdigit()) | admins
    for channel in db.get_channels().values():
        user_ids.add(channel_rental_user_id(channel))
    user_ids.discard(0)
    if not user_ids:
        await message.answer("Клієнтів ще немає.")
        return
    lines = ["<b>👥 Клієнти</b>"]
    for user_id in sorted(user_ids):
        lines.append(format_client_line(user_id, rentals.get(str(user_id))))
    lines.append("\nДеталі: <code>/client user_id</code>")
    await message.answer("\n".join(lines))


@router.message(Command("client"))
@owner_only_message
async def cmd_client(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Приклад: <code>/client 123456789</code>")
        return
    await message.answer(client_details_text(int(parts[1])))


@router.message(Command("extend"))
@owner_only_message
async def cmd_extend(message: Message) -> None:
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer(
            "Формат: <code>/extend user_id days [basic|pro|vip]</code>\n"
            "Приклад: <code>/extend 123456789 30 pro</code>"
        )
        return
    user_id = int(parts[1])
    days = max(1, int(parts[2]))
    current = db.get_user_rental(user_id)
    plan_id = normalize_plan_id(parts[3] if len(parts) == 4 else (current or {}).get("plan"))
    current_until = format_paid_until((current or {}).get("paid_until"))
    base = datetime.now(timezone.utc)
    current_paid_until = None
    if current:
        current_paid_until = parse_paid_until(current.get("paid_until"))
    if current_paid_until and current_paid_until > base:
        base = current_paid_until
    paid_until = (base + timedelta(days=days)).isoformat()
    db.add_admin(user_id)
    rental = dict(current or {"user_id": user_id})
    rental.update(
        {
            "user_id": user_id,
            "plan": plan_id,
            "plan_title": plan_title(plan_id),
            "channel_limit": plan_channel_limit(plan_id),
            "paid_until": paid_until,
            "manual_extended_at": datetime.now(timezone.utc).isoformat(),
            "manual_extended_days": days,
            "banned": False,
            "reminders_sent": [],
        }
    )
    db.upsert_user_rental(user_id, rental)
    await message.answer(
        f"✅ Доступ продовжено для <code>{user_id}</code>.\n"
        f"Було: <b>{h(current_until)}</b>\n"
        f"Тариф: <b>{h(plan_title(plan_id))}</b>\n"
        f"Тепер до: <b>{h(format_paid_until(paid_until))}</b>"
    )


@router.message(Command("trial"))
@owner_only_message
async def cmd_trial(message: Message) -> None:
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer(
            "Формат: <code>/trial user_id days [basic|pro|vip]</code>\n"
            "Приклад: <code>/trial 123456789 3 basic</code>"
        )
        return
    user_id = int(parts[1])
    days = max(1, int(parts[2]))
    plan_id = normalize_plan_id(parts[3] if len(parts) == 4 else "basic")
    paid_until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    db.add_admin(user_id)
    db.upsert_user_rental(
        user_id,
        {
            "user_id": user_id,
            "plan": plan_id,
            "plan_title": plan_title(plan_id),
            "channel_limit": plan_channel_limit(plan_id),
            "paid_until": paid_until,
            "trial": True,
            "trial_started_at": datetime.now(timezone.utc).isoformat(),
            "banned": False,
            "reminders_sent": [],
        },
    )
    await message.answer(
        f"✅ Trial видано для <code>{user_id}</code>.\n"
        f"Тариф: <b>{h(plan_title(plan_id))}</b>\n"
        f"Активний до: <b>{h(format_paid_until(paid_until))}</b>"
    )


@router.message(Command("ban"))
@owner_only_message
async def cmd_ban(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: <code>/ban user_id [причина]</code>")
        return
    user_id = int(parts[1])
    if user_id == OWNER_ID:
        await message.answer("Owner не можна заблокувати.")
        return
    reason = parts[2].strip() if len(parts) == 3 else ""
    db.update_user_rental(
        user_id,
        banned=True,
        ban_reason=reason,
        banned_at=datetime.now(timezone.utc).isoformat(),
    )
    await message.answer(f"⛔ Клієнта <code>{user_id}</code> заблоковано.")


@router.message(Command("unban"))
@owner_only_message
async def cmd_unban(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: <code>/unban user_id</code>")
        return
    user_id = int(parts[1])
    db.update_user_rental(user_id, banned=False, ban_reason="", unbanned_at=datetime.now(timezone.utc).isoformat())
    await message.answer(f"✅ Клієнта <code>{user_id}</code> розблоковано.")


@router.message(Command("income"))
@owner_only_message
async def cmd_income(message: Message) -> None:
    paid = [payment for payment in db.get_payments().values() if payment.get("status") == "paid"]
    total = sum(int(payment.get("amount", 0) or 0) for payment in paid)
    by_plan: dict[str, int] = defaultdict(int)
    for payment in paid:
        by_plan[normalize_plan_id(payment.get("plan"))] += int(payment.get("amount", 0) or 0)
    lines = [
        "<b>💰 Дохід Stars</b>",
        f"Усього оплат: <b>{len(paid)}</b>",
        f"Усього Stars: <b>{total}</b>",
        "",
        "<b>По тарифах:</b>",
    ]
    for plan_id in ("basic", "pro", "vip"):
        lines.append(f"• {h(plan_title(plan_id))}: <b>{by_plan[plan_id]}</b> Stars")
    await message.answer("\n".join(lines))


@router.message(Command("payments_history"))
@owner_only_message
async def cmd_payments_history(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    limit = 10
    if len(parts) == 2 and parts[1].isdigit():
        limit = max(1, min(50, int(parts[1])))
    payments = list(db.get_payments().values())
    payments.sort(key=lambda item: item.get("paid_at") or item.get("created_at") or "", reverse=True)
    if not payments:
        await message.answer("Історії оплат ще немає.")
        return
    lines = [f"<b>🧾 Останні платежі ({limit})</b>"]
    for payment in payments[:limit]:
        status = payment.get("status", "unknown")
        user_id = payment.get("user_id", "-")
        amount = payment.get("amount", 0)
        plan_id = normalize_plan_id(payment.get("plan"))
        created = payment.get("paid_at") or payment.get("created_at") or "-"
        lines.append(
            f"• <code>{h(user_id)}</code> — <b>{h(status)}</b>, "
            f"{h(plan_title(plan_id))}, <b>{h(amount)} XTR</b>, {h(created[:19])}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("backup"))
@owner_only_message
async def cmd_backup(message: Message) -> None:
    archive = create_backup()
    if not archive:
        await message.answer("Немає даних для бекапу.")
        return
    await message.answer(f"✅ Бекап створено: <code>{h(archive.name)}</code>\nПапка: <code>backups</code>")


@router.message(Command("upload"))
@admin_only_message
async def cmd_upload(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    key = command_target(message, parts[1] if len(parts) == 2 else None)
    if key not in db.get_channels() or not can_access_channel(message.from_user.id if message.from_user else 0, key):
        await message.answer(
            "Профіль не знайдено.\n"
            "У команді <code>/upload key</code> треба вказувати саме <code>key</code>, створений через <code>/addchannel</code>.\n"
            "Приклад: <code>/upload HOTBOYS_YAOI_NS</code>\n\n"
            "Список профілів: /channels"
        )
        return
    upload_sessions[message.from_user.id] = key
    await message.answer(
        f"📥 Завантаження для профілю <code>{h(key)}</code> увімкнено.\n"
        f"Файли будуть збережені в папку <code>channels/{h(key)}</code>.\n"
        "Надсилай фото, відео або медіафайли як документи.\n"
        "Завершити: /upload_stop"
    )


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
    if not has_active_rental(user_id):
        upload_sessions.pop(user_id, None)
        await answer_rental_required(message)
        return
    channel = db.get_channel(key)
    if not channel or not can_access_channel(user_id, key, channel):
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
    if not db.get_channel(key) or not can_access_channel(message.from_user.id if message.from_user else 0, key):
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
    if not channel or not can_access_channel(message.from_user.id if message.from_user else 0, key, channel):
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
    await safe_edit_text(
        callback.message,
        "<b>📢 Обери канал</b>",
        reply_markup=channels_keyboard(visible_channels(callback.from_user.id)),
    )
    await callback.answer()


@router.callback_query(F.data == "rental")
@admin_only_callback
async def cb_rental(callback: CallbackQuery) -> None:
    rental = db.get_user_rental(callback.from_user.id)
    await safe_edit_text(
        callback.message,
        "<b>⭐ Оренда бота</b>\n\n"
        f"{plans_help_text()}\n\n"
        f"{rental_status_text(callback.from_user.id, rental)}\n"
        f"{user_channel_limit_text(callback.from_user.id, rental)}",
        reply_markup=rental_plans_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "add_help")
@admin_only_callback
async def cb_add_help(callback: CallbackQuery) -> None:
    await callback.message.answer(addchannel_help_text())
    await callback.answer()


@router.callback_query(F.data == "status_active")
@admin_only_callback
async def cb_status_active(callback: CallbackQuery) -> None:
    key, channel = get_active_channel(callback.from_user.id)
    if not channel:
        await callback.message.answer("Каналів ще немає.\n\n" + addchannel_help_text())
        await callback.answer()
        return
    await callback.message.answer(channel_summary(key, channel), reply_markup=channel_controls(key, channel.get("paused", False)))
    await callback.answer("Оновлено")


@router.callback_query(F.data.startswith("rentplan:"))
@admin_only_callback
async def cb_rent_plan(callback: CallbackQuery) -> None:
    if callback.from_user.id == OWNER_ID:
        await callback.answer("Owner користується ботом без оплати.", show_alert=True)
        return
    rental = db.get_user_rental(callback.from_user.id)
    if is_rental_banned(rental):
        await callback.answer("Ти заблокований owner. Оплата недоступна.", show_alert=True)
        return
    plan_id = normalize_plan_id(callback.data.split(":", 1)[1])
    plan = get_plan(plan_id)
    payload = f"rent_bot:{uuid4().hex}"
    db.upsert_payment(
        payload,
        {
            "status": "pending",
            "kind": "rent_bot",
            "user_id": callback.from_user.id,
            "plan": plan_id,
            "amount": int(plan["stars"]),
            "currency": "XTR",
            "rental_days": int(plan["days"]),
            "channel_limit": int(plan["channel_limit"]),
            "current_paid_until": rental.get("paid_until") if rental else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await callback.message.answer(
        f"⭐ Тариф: <b>{h(plan_text(plan_id))}</b>\n"
        "Після оплати доступ активується автоматично."
    )
    await send_bot_rental_invoice(callback.message, payload=payload, plan_id=plan_id)
    await callback.answer("Рахунок створено")


@router.callback_query(F.data.startswith("select:"))
@admin_only_callback
async def cb_select(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 1)[1]
    channel = db.get_channel(key)
    if not channel or not can_access_channel(callback.from_user.id, key, channel):
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    active_channels[callback.from_user.id] = key
    await safe_edit_text(callback.message, channel_summary(key, channel), reply_markup=channel_controls(key, channel.get("paused", False)))
    await callback.answer()


@router.callback_query(F.data.startswith("send:"))
@admin_only_callback
async def cb_send(callback: CallbackQuery, bot: Bot) -> None:
    key = callback.data.split(":", 1)[1]
    channel = db.get_channel(key)
    if not channel or not can_access_channel(callback.from_user.id, key, channel):
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
    if not can_access_channel(callback.from_user.id, key):
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    if not db.update_channel(key, paused=paused):
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    channel = db.get_channel(key)
    await safe_edit_text(callback.message, channel_summary(key, channel), reply_markup=channel_controls(key, paused))
    await callback.answer("⏸ Пауза" if paused else "▶️ Активовано")


@router.callback_query(F.data.startswith("interval:"))
@admin_only_callback
async def cb_interval(callback: CallbackQuery) -> None:
    _, key, minutes = callback.data.split(":", 2)
    if not can_access_channel(callback.from_user.id, key):
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    if not db.update_channel(key, interval_minutes=int(minutes), last_attempt=None):
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    channel = db.get_channel(key)
    await safe_edit_text(callback.message, channel_summary(key, channel), reply_markup=channel_controls(key, channel.get("paused", False)))
    await callback.answer(f"Інтервал: {minutes} хв")


@router.callback_query(F.data.startswith("status:"))
@admin_only_callback
async def cb_status(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 1)[1]
    channel = db.get_channel(key)
    if not channel or not can_access_channel(callback.from_user.id, key, channel):
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    await safe_edit_text(callback.message, channel_summary(key, channel), reply_markup=channel_controls(key, channel.get("paused", False)))
    await callback.answer("Оновлено")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
