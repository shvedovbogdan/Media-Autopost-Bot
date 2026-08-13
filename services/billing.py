from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config import (
    BOT_RENTAL_DAYS,
    BOT_RENTAL_STARS,
    OWNER_ID,
    RENTAL_BASIC_CHANNELS,
    RENTAL_BASIC_STARS,
    RENTAL_PRO_CHANNELS,
    RENTAL_PRO_STARS,
    RENTAL_VIP_CHANNELS,
    RENTAL_VIP_STARS,
)


RENTAL_PLANS = {
    "basic": {
        "id": "basic",
        "title": "Basic",
        "stars": RENTAL_BASIC_STARS,
        "days": BOT_RENTAL_DAYS,
        "channel_limit": RENTAL_BASIC_CHANNELS,
        "description": f"до {RENTAL_BASIC_CHANNELS} каналу",
    },
    "pro": {
        "id": "pro",
        "title": "Pro",
        "stars": RENTAL_PRO_STARS,
        "days": BOT_RENTAL_DAYS,
        "channel_limit": RENTAL_PRO_CHANNELS,
        "description": f"до {RENTAL_PRO_CHANNELS} каналів",
    },
    "vip": {
        "id": "vip",
        "title": "VIP",
        "stars": RENTAL_VIP_STARS,
        "days": BOT_RENTAL_DAYS,
        "channel_limit": RENTAL_VIP_CHANNELS,
        "description": f"до {RENTAL_VIP_CHANNELS} каналів",
    },
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_paid_until(value: object) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value))
        return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
    except (TypeError, ValueError):
        return None


def is_owner_user(user_id: int | str | None) -> bool:
    try:
        return bool(OWNER_ID and user_id and int(user_id) == OWNER_ID)
    except (TypeError, ValueError):
        return False


def is_rental_active(rental: dict | None) -> bool:
    if not rental:
        return False
    if rental.get("banned", False):
        return False
    paid_until = parse_paid_until(rental.get("paid_until"))
    return bool(paid_until and paid_until > now_utc())


def user_has_active_bot_rental(user_id: int | str | None, rental: dict | None) -> bool:
    return is_owner_user(user_id) or is_rental_active(rental)


def new_rental_until() -> str:
    return (now_utc() + timedelta(days=BOT_RENTAL_DAYS)).isoformat()


def renewed_rental_until(current_value: object) -> str:
    current = parse_paid_until(current_value)
    base = current if current and current > now_utc() else now_utc()
    return (base + timedelta(days=BOT_RENTAL_DAYS)).isoformat()


def normalize_plan_id(plan_id: object | None) -> str:
    value = str(plan_id or "basic").strip().lower()
    return value if value in RENTAL_PLANS else "basic"


def get_plan(plan_id: object | None) -> dict:
    return RENTAL_PLANS[normalize_plan_id(plan_id)]


def plan_title(plan_id: object | None) -> str:
    return str(get_plan(plan_id)["title"])


def plan_price(plan_id: object | None) -> int:
    return int(get_plan(plan_id)["stars"])


def plan_days(plan_id: object | None) -> int:
    return int(get_plan(plan_id)["days"])


def plan_channel_limit(plan_id: object | None) -> int:
    return int(get_plan(plan_id)["channel_limit"])


def plan_text(plan_id: object | None) -> str:
    plan = get_plan(plan_id)
    return f"{plan['title']} — {plan['stars']} Stars / {plan['days']} днів / {plan['description']}"


def plans_help_text() -> str:
    return "\n".join(f"• <code>{plan_id}</code>: {plan_text(plan_id)}" for plan_id in ("basic", "pro", "vip"))


def renewed_rental_until_for_plan(current_value: object, plan_id: object | None) -> str:
    current = parse_paid_until(current_value)
    base = current if current and current > now_utc() else now_utc()
    return (base + timedelta(days=plan_days(plan_id))).isoformat()


def is_rental_banned(rental: dict | None) -> bool:
    return bool(rental and rental.get("banned", False))


def rental_plan_id(rental: dict | None) -> str:
    return normalize_plan_id(rental.get("plan") if rental else None)


def rental_channel_limit(rental: dict | None) -> int:
    if rental and rental.get("channel_limit"):
        try:
            return int(rental["channel_limit"])
        except (TypeError, ValueError):
            pass
    return plan_channel_limit(rental_plan_id(rental))


# Backward-compatible aliases for older per-channel invoices.
def new_paid_until() -> str:
    return new_rental_until()


def renewed_paid_until(current_value: object) -> str:
    return renewed_rental_until(current_value)


def channel_rental_user_id(channel: dict) -> int:
    for field in ("rental_user_id", "created_by", "billing_user_id"):
        value = channel.get(field)
        try:
            if value:
                return int(value)
        except (TypeError, ValueError):
            continue
    return OWNER_ID


def is_legacy_channel_payment_active(channel: dict) -> bool:
    if not channel.get("payment_required", False):
        return True
    paid_until = parse_paid_until(channel.get("paid_until"))
    return bool(paid_until and paid_until > now_utc())


def channel_access_error(channel: dict, rental: dict | None, key: str = "key") -> str | None:
    if channel.get("payment_required", False):
        if is_legacy_channel_payment_active(channel):
            return None
        return f"Підписка на канал закінчилась. Продовження: /renewchannel {key}"
    rental_user_id = channel_rental_user_id(channel)
    if user_has_active_bot_rental(rental_user_id, rental):
        return None
    return (
        "Оренда бота для цього клієнта закінчилась. "
        "Канали не будуть публікувати, доки клієнт не оплатить /rentbot"
    )


def format_paid_until(value: object) -> str:
    paid_until = parse_paid_until(value)
    if not paid_until:
        return "не оплачено"
    return paid_until.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def rent_price_text(plan_id: object | None = None) -> str:
    if plan_id:
        plan = get_plan(plan_id)
        return f"{plan['stars']} Stars / {plan['days']} днів"
    return f"від {BOT_RENTAL_STARS} Stars / {BOT_RENTAL_DAYS} днів"


def price_text() -> str:
    return rent_price_text()


def rental_status_text(user_id: int | str | None, rental: dict | None) -> str:
    if is_owner_user(user_id):
        return "Оренда бота: <b>не потрібна для owner</b>"
    if is_rental_banned(rental):
        return "Оренда бота: <b>клієнт заблокований owner</b>"
    if is_rental_active(rental):
        plan_id = rental_plan_id(rental)
        return (
            f"Оренда бота: <b>{plan_title(plan_id)} активний до {format_paid_until(rental.get('paid_until'))}</b> "
            f"(ліміт каналів: {plan_channel_limit(plan_id)})"
        )
    return "Оренда бота: <b>не оплачена або закінчилась</b>. Оплатити: <code>/rentbot</code>"


def channel_billing_status_line(channel: dict, rental: dict | None, key: str = "key") -> str:
    if channel.get("payment_required", False):
        if is_legacy_channel_payment_active(channel):
            return f"Оплата каналу: <b>активна до {format_paid_until(channel.get('paid_until'))}</b>"
        return f"Оплата каналу: <b>закінчилась</b>. Продовжити: <code>/renewchannel {key}</code>"
    rental_user_id = channel_rental_user_id(channel)
    return rental_status_text(rental_user_id, rental)
