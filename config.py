from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project paths / Шляхи проєкту
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
STATS_DIR = BASE_DIR / "stats"
CAPTION_HISTORY_DIR = BASE_DIR / "caption_history"
CHANNELS_DIR = BASE_DIR / "channels"
CAPTION_PACKS_DIR = BASE_DIR / "caption_packs"
CHANNELS_PATH = BASE_DIR / "channels.json"
ADMINS_PATH = DATA_DIR / "admins.json"


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment value. / Читає логічне значення з .env."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    """Read an integer safely. / Безпечно читає ціле число з .env."""
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = env_int("OWNER_ID", 0)
BOT_LANGUAGE = os.getenv("BOT_LANGUAGE", "ua").strip().lower()
TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv").strip()
AUTO_START = env_bool("AUTO_START", True)
NOTIFY_OWNER = env_bool("NOTIFY_OWNER", True)
SCHEDULER_POLL_SECONDS = max(5, env_int("SCHEDULER_POLL_SECONDS", 20))

PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")
DOCUMENT_MEDIA_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS


def parse_admin_ids() -> set[int]:
    """Parse comma/semicolon-separated admins. / Читає ID додаткових адміністраторів."""
    raw = os.getenv("ADMIN_IDS", "")
    result: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    if OWNER_ID:
        result.add(OWNER_ID)
    return result


ENV_ADMIN_IDS = parse_admin_ids()


def validate_environment() -> None:
    """Fail early with a useful message. / Одразу показує зрозумілу помилку налаштувань."""
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_BOT_TOKEN_HERE":
        raise RuntimeError("BOT_TOKEN не налаштовано. Скопіюй .env.example у .env та встав токен BotFather.")
    if not OWNER_ID:
        raise RuntimeError("OWNER_ID не налаштовано. Вкажи свій цифровий Telegram ID у .env.")
