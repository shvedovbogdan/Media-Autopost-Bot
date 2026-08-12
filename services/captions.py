from __future__ import annotations

import html
import json
import random
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import CAPTION_PACKS_DIR, TIMEZONE
from database import JsonDatabase

db = JsonDatabase()


CAPTIONS = {
    "ua": {
        "morning": [
            "Доброго ранку 🔥 Хто вже прокинувся?",
            "Новий день — новий привід заглянути сюди 😉",
            "Ранкова порція настрою вже тут ☀️",
            "Поки всі прокидаються — ми вже починаємо 👀",
            "Доброго ранку 😏 Сьогодні буде цікаво",
            "Свіжий ранок заслуговує на свіжий пост 🔥",
            "Хто тут найперший? Ловіть ранковий бонус",
            "Почнемо цей день із правильного настрою ✨",
        ],
        "day": [
            "Невелика перерва? Тоді вам сюди 👀",
            "День стає цікавішим прямо зараз 🔥",
            "Щось новеньке посеред дня — саме те 😉",
            "Стрічка просила продовження… ми не відмовили 😏",
            "Ще один пост для вашого настрою",
            "Хто казав, що вдень має бути нудно? 👀",
            "Свіженьке вже тут. Не проходьте повз 🔥",
            "Трохи контенту, щоб день минав швидше",
        ],
        "evening": [
            "Вечір тільки починається… 😏",
            "Саме час трохи розслабитися 🔥",
            "Після довгого дня вам точно потрібен цей пост 👀",
            "Вечірній настрій завантажено 😉",
            "Що краще за вечір із новим постом?",
            "Готові до вечірньої порції контенту?",
            "Темнішає надворі — а тут стає цікавіше 🔥",
            "Вечір створений для таких моментів ✨",
        ],
        "night": [
            "Хто ще не спить? Тоді це для вас 🌙",
            "Усі сплять… а ми продовжуємо 🔥",
            "Ніч тільки починається 👀",
            "Тихіше… зараз буде цікаво 🤫",
            "Для тих, хто любить нічні сюрпризи 😈",
            "Не спиться? Є чим зайнятись 😉",
            "Після опівночі все стає цікавішим 🌙🔥",
            "Якщо ви ще тут — цей пост саме для вас",
        ],
        "photo": [
            "📸 Свіжий кадр уже тут",
            "📸 Один кадр — і настрій змінено 🔥",
            "📸 Ловіть цей момент 👀",
            "📸 Просто залишимо це тут…",
            "📸 Цей кадр вартий вашої уваги",
            "📸 Ще один привід затриматися тут 😉",
            "📸 Без зайвих слів. Просто дивіться",
            "📸 Камера точно знала, що робить 😏",
        ],
        "video": [
            "🎥 Натискайте play — далі цікавіше 🔥",
            "🎥 Свіжий ролик уже чекає",
            "🎥 Це варто подивитися до кінця 👀",
            "🎥 Готові? Тисніть play ▶️",
            "🎥 Трохи руху у вашу стрічку",
            "🎥 Звук увімкнули? Тоді вперед 😉",
            "🎥 Свіжий ролик без зайвих слів",
            "🎥 Відео, повз яке складно пройти 😏",
        ],
        "cta": [
            "🔥 Залишайте реакцію, якщо сподобалось",
            "👀 Ну як вам? Цікаво почути вашу думку",
            "❤️ Покажіть, що хочете більше такого контенту",
            "😏 Хто хоче продовження? Показуйте активність",
            "💬 Напишіть, який формат подобається більше",
            "👀 Залишайтесь — далі буде цікавіше",
            "🔥 Більше реакцій — більше нових постів",
            "👇 Не соромтеся показати свою реакцію",
        ],
    },
    "ru": {
        "morning": [
            "Доброе утро 🔥 Кто уже проснулся?",
            "Новый день — новый повод заглянуть сюда 😉",
            "Утренняя порция настроения уже здесь ☀️",
            "Пока все просыпаются — мы уже начинаем 👀",
            "Доброе утро 😏 Сегодня будет интересно",
            "Свежее утро заслуживает свежий пост 🔥",
            "Кто здесь самый первый? Ловите утренний бонус",
            "Начнём этот день с правильного настроения ✨",
        ],
        "day": [
            "Небольшой перерыв? Тогда вам сюда 👀",
            "День становится интереснее прямо сейчас 🔥",
            "Что-то новенькое посреди дня — самое то 😉",
            "Лента просила продолжения… мы не отказали 😏",
            "Ещё один пост для вашего настроения",
            "Кто сказал, что днём должно быть скучно? 👀",
            "Свеженькое уже здесь. Не проходите мимо 🔥",
            "Немного контента, чтобы день шёл быстрее",
        ],
        "evening": [
            "Вечер только начинается… 😏",
            "Самое время немного расслабиться 🔥",
            "После долгого дня вам нужен этот пост 👀",
            "Вечернее настроение загружено 😉",
            "Что лучше вечера с новым постом?",
            "Готовы к вечерней порции контента?",
            "Темнеет снаружи — а здесь интереснее 🔥",
            "Вечер создан для таких моментов ✨",
        ],
        "night": [
            "Кто ещё не спит? Тогда это для вас 🌙",
            "Все спят… а мы продолжаем 🔥",
            "Ночь только начинается 👀",
            "Тише… сейчас будет интересно 🤫",
            "Для тех, кто любит ночные сюрпризы 😈",
            "Не спится? Есть чем заняться 😉",
            "После полуночи всё становится интереснее 🌙🔥",
            "Если вы ещё здесь — этот пост для вас",
        ],
        "photo": [
            "📸 Свежий кадр уже здесь",
            "📸 Один кадр — и настроение изменилось 🔥",
            "📸 Ловите этот момент 👀",
            "📸 Просто оставим это здесь…",
            "📸 Этот кадр стоит вашего внимания",
            "📸 Ещё один повод задержаться здесь 😉",
            "📸 Без лишних слов. Просто смотрите",
            "📸 Камера точно знала, что делает 😏",
        ],
        "video": [
            "🎥 Нажимайте play — дальше интереснее 🔥",
            "🎥 Свежий ролик уже ждёт",
            "🎥 Это стоит посмотреть до конца 👀",
            "🎥 Готовы? Нажимайте play ▶️",
            "🎥 Немного движения в вашу ленту",
            "🎥 Звук включили? Тогда вперёд 😉",
            "🎥 Свежий ролик без лишних слов",
            "🎥 Видео, мимо которого сложно пройти 😏",
        ],
        "cta": [
            "🔥 Оставляйте реакцию, если понравилось",
            "👀 Ну как вам? Интересно узнать ваше мнение",
            "❤️ Покажите, что хотите больше такого контента",
            "😏 Кто хочет продолжение? Показывайте активность",
            "💬 Напишите, какой формат нравится больше",
            "👀 Оставайтесь — дальше будет интереснее",
            "🔥 Больше реакций — больше новых постов",
            "👇 Не стесняйтесь показать свою реакцию",
        ],
    },
    "en": {
        "morning": [
            "Good morning 🔥 Who's already awake?",
            "New day, new reason to stop by 😉",
            "Your morning mood boost is here ☀️",
            "While everyone wakes up, we're getting started 👀",
            "Good morning 😏 Today looks interesting",
            "A fresh morning deserves a fresh post 🔥",
            "Who's here first? Catch this morning bonus",
            "Let's start the day with the right mood ✨",
        ],
        "day": [
            "Taking a little break? You're in the right place 👀",
            "Making your day more interesting right now 🔥",
            "Something fresh for the middle of your day 😉",
            "Your feed asked for more… we couldn't say no 😏",
            "Another post to lift your mood",
            "Who said daytime had to be boring? 👀",
            "Something fresh is here. Don't scroll past 🔥",
            "A little content to make the day go faster",
        ],
        "evening": [
            "The evening is just getting started… 😏",
            "Time to relax a little 🔥",
            "After a long day, you deserve this post 👀",
            "Evening mood: activated 😉",
            "What's better than an evening with something new?",
            "Ready for some evening content?",
            "It's darker outside and more interesting here 🔥",
            "Some moments are made for the evening ✨",
        ],
        "night": [
            "Who's still awake? This one's for you 🌙",
            "Everyone's asleep… we're still here 🔥",
            "The night is only getting started 👀",
            "Shhh… things are about to get interesting 🤫",
            "For those who love late-night surprises 😈",
            "Can't sleep? Here's something for you 😉",
            "Everything feels better after midnight 🌙🔥",
            "If you're still here, this post is for you",
        ],
        "photo": [
            "📸 A fresh shot just landed",
            "📸 One shot, instant mood 🔥",
            "📸 Catch this moment 👀",
            "📸 Just leaving this here…",
            "📸 This shot deserves your attention",
            "📸 Another reason to stay a little longer 😉",
            "📸 No words needed. Just look",
            "📸 The camera knew what it was doing 😏",
        ],
        "video": [
            "🎥 Hit play — it gets better from here 🔥",
            "🎥 A fresh clip just dropped",
            "🎥 This one is worth watching to the end 👀",
            "🎥 Ready? Press play ▶️",
            "🎥 A little movement for your feed",
            "🎥 Sound on? Then let's go 😉",
            "🎥 Fresh video, no extra words needed",
            "🎥 A clip that's hard to scroll past 😏",
        ],
        "cta": [
            "🔥 Drop a reaction if you liked it",
            "👀 What do you think? Let us know",
            "❤️ Show some love if you want more",
            "😏 Want another one? Show some activity",
            "💬 Tell us which format you like more",
            "👀 Stay tuned — it gets more interesting",
            "🔥 More reactions mean more fresh posts",
            "👇 Don't be shy — leave a reaction",
        ],
    },
}


_pack_cache: dict[str, dict] = {"default": CAPTIONS}


def load_caption_pack(name: str) -> dict:
    """Load a channel-specific caption pack. / Завантажує окремий набір підписів каналу."""
    safe_name = re.sub(r"[^a-z0-9_-]", "", (name or "default").lower()) or "default"
    if safe_name in _pack_cache:
        return _pack_cache[safe_name]
    path = CAPTION_PACKS_DIR / f"{safe_name}.json"
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or not all(lang in data for lang in ("ua", "ru", "en")):
            raise ValueError("caption pack has an invalid structure")
        _pack_cache[safe_name] = data
    except (OSError, ValueError, json.JSONDecodeError):
        _pack_cache[safe_name] = CAPTIONS
    return _pack_cache[safe_name]


def period() -> str:
    """Return the local time period. / Повертає частину доби в налаштованому часовому поясі."""
    try:
        hour = datetime.now(ZoneInfo(TIMEZONE)).hour
    except ZoneInfoNotFoundError:
        hour = datetime.now(timezone.utc).hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def normalize(text: str) -> str:
    text = re.sub(r"[^\w\sа-яіїєґ]", "", text.lower().strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text)


def clean_file_name(file_name: str) -> str:
    """Alex_Smith_final.jpg -> Alex Smith / Очищає технічну назву файлу."""
    if not file_name:
        return ""
    name = Path(file_name).stem.replace("_", " ").replace("-", " ")
    name = re.sub(r"\b(final|copy|edited|edit|new|resize|resized|compressed)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    return html.escape(name)


def too_similar(text: str, history: list[dict], threshold: float = 0.72) -> bool:
    current = normalize(text)
    for item in history[-60:]:
        old = normalize(item.get("text", ""))
        if old and (old == current or SequenceMatcher(None, current, old).ratio() >= threshold):
            return True
    return False


def generate_caption(
    channel_key: str,
    media_type: str,
    lang: str = "en",
    footer: str = "",
    file_name: str = "",
    caption_pack: str = "default",
) -> str:
    """Create a varied caption and avoid recent repeats. / Створює різні підписи без повторів."""
    pack = load_caption_pack(caption_pack)
    lang = lang if lang in pack else "en"
    media_type = media_type if media_type in {"photo", "video"} else "photo"
    parts = pack[lang]
    history = db.get_caption_history(channel_key)
    display_name = clean_file_name(file_name)

    for _ in range(60):
        lines = [random.choice(parts[period()]), random.choice(parts[media_type])]
        if display_name:
            lines.extend(["", f"👤 {display_name}"])
        lines.extend(["", random.choice(parts["cta"])])
        core = "\n".join(lines)
        if not too_similar(core, history):
            db.add_caption_history(channel_key, core)
            suffix = f"\n\n{html.escape(footer.strip())}" if footer.strip() else ""
            return (core + suffix)[:1024]

    fallback = {
        "ua": "🔥 Новий пост уже тут.\n\n❤️ Покажіть реакцією, як вам!",
        "ru": "🔥 Новый пост уже здесь.\n\n❤️ Покажите реакцией, как вам!",
        "en": "🔥 A new post just dropped.\n\n❤️ Drop a reaction if you like it!",
    }[lang]
    if display_name:
        fallback = f"{fallback.splitlines()[0]}\n\n👤 {display_name}\n\n" + "\n".join(fallback.splitlines()[2:])
    db.add_caption_history(channel_key, fallback)
    suffix = f"\n\n{html.escape(footer.strip())}" if footer.strip() else ""
    return (fallback + suffix)[:1024]
