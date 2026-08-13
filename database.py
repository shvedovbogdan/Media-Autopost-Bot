from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from config import (
    ADMINS_PATH,
    BACKUP_STATE_PATH,
    BOT_RENTALS_PATH,
    CAPTION_HISTORY_DIR,
    CHANNELS_PATH,
    ENV_ADMIN_IDS,
    PAYMENTS_PATH,
    STATS_DIR,
)
from utils.json_store import read_json, write_json


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonDatabase:
    """Small shared JSON storage. / Невелике спільне JSON-сховище."""

    _lock = threading.RLock()

    def __init__(self) -> None:
        STATS_DIR.mkdir(parents=True, exist_ok=True)
        CAPTION_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        ADMINS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PAYMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        BOT_RENTALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        BACKUP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Admins / Адміністратори
    def get_admins(self) -> set[int]:
        data = read_json(ADMINS_PATH, {"admins": []})
        if not isinstance(data, dict):
            data = {"admins": []}
        saved = {int(value) for value in data.get("admins", []) if str(value).isdigit()}
        return ENV_ADMIN_IDS | saved

    def add_admin(self, user_id: int) -> None:
        with self._lock:
            admins = self.get_admins()
            admins.add(int(user_id))
            write_json(ADMINS_PATH, {"admins": sorted(admins)})

    def remove_admin(self, user_id: int) -> None:
        with self._lock:
            admins = self.get_admins()
            admins.discard(int(user_id))
            write_json(ADMINS_PATH, {"admins": sorted(admins)})

    # Channels / Канали
    def get_channels(self) -> dict[str, dict[str, Any]]:
        data = read_json(CHANNELS_PATH, {})
        return data if isinstance(data, dict) else {}

    def save_channels(self, channels: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            write_json(CHANNELS_PATH, channels)

    def get_channel(self, key: str) -> dict[str, Any] | None:
        return self.get_channels().get(key)

    def upsert_channel(self, key: str, channel_data: dict[str, Any]) -> None:
        with self._lock:
            channels = self.get_channels()
            channels[key] = channel_data
            write_json(CHANNELS_PATH, channels)

    def update_channel(self, key: str, **updates: Any) -> bool:
        with self._lock:
            channels = self.get_channels()
            if key not in channels:
                return False
            channels[key].update(updates)
            write_json(CHANNELS_PATH, channels)
            return True

    def delete_channel(self, key: str) -> bool:
        """Delete config only; media stays on disk. / Видаляє лише конфіг, медіа залишаються."""
        with self._lock:
            channels = self.get_channels()
            if key not in channels:
                return False
            del channels[key]
            write_json(CHANNELS_PATH, channels)
            return True

    # Stars payments / Оплати Telegram Stars
    def get_payments(self) -> dict[str, dict[str, Any]]:
        data = read_json(PAYMENTS_PATH, {})
        return data if isinstance(data, dict) else {}

    def get_payment(self, payload: str) -> dict[str, Any] | None:
        return self.get_payments().get(payload)

    def upsert_payment(self, payload: str, payment_data: dict[str, Any]) -> None:
        with self._lock:
            payments = self.get_payments()
            payments[payload] = payment_data
            write_json(PAYMENTS_PATH, payments)

    def update_payment(self, payload: str, **updates: Any) -> bool:
        with self._lock:
            payments = self.get_payments()
            if payload not in payments:
                return False
            payments[payload].update(updates)
            write_json(PAYMENTS_PATH, payments)
            return True

    # Bot rentals / Оренда бота
    def get_bot_rentals(self) -> dict[str, dict[str, Any]]:
        data = read_json(BOT_RENTALS_PATH, {})
        return data if isinstance(data, dict) else {}

    def get_user_rental(self, user_id: int | str) -> dict[str, Any] | None:
        return self.get_bot_rentals().get(str(user_id))

    def upsert_user_rental(self, user_id: int | str, rental_data: dict[str, Any]) -> None:
        with self._lock:
            rentals = self.get_bot_rentals()
            rentals[str(user_id)] = rental_data
            write_json(BOT_RENTALS_PATH, rentals)

    def update_user_rental(self, user_id: int | str, **updates: Any) -> dict[str, Any]:
        with self._lock:
            rentals = self.get_bot_rentals()
            rental = rentals.get(str(user_id), {"user_id": int(user_id)})
            rental.update(updates)
            rentals[str(user_id)] = rental
            write_json(BOT_RENTALS_PATH, rentals)
            return rental

    # Backup state / Стан автобекапу
    def get_backup_state(self) -> dict[str, Any]:
        data = read_json(BACKUP_STATE_PATH, {})
        return data if isinstance(data, dict) else {}

    def save_backup_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            write_json(BACKUP_STATE_PATH, state)

    # Stats and caption history / Статистика та історія підписів
    def stats_path(self, key: str):
        return STATS_DIR / f"{key}_stats.json"

    def history_path(self, key: str):
        return CAPTION_HISTORY_DIR / f"{key}_history.json"

    def add_stat(self, key: str, media_type: str, file_name: str, caption: str, fingerprint: str | None = None) -> None:
        with self._lock:
            stats = read_json(self.stats_path(key), [])
            if not isinstance(stats, list):
                stats = []
            stats.append(
                {
                    "channel": key,
                    "type": media_type,
                    "file": file_name,
                    "fingerprint": fingerprint,
                    "caption": caption,
                    "timestamp": now_iso(),
                }
            )
            cutoff = datetime.now(timezone.utc) - timedelta(days=60)
            filtered: list[dict[str, Any]] = []
            for item in stats:
                try:
                    timestamp = datetime.fromisoformat(item.get("timestamp", ""))
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    if timestamp >= cutoff:
                        filtered.append(item)
                except (TypeError, ValueError):
                    continue
            write_json(self.stats_path(key), filtered)

    def get_stats(self, key: str) -> list[dict[str, Any]]:
        data = read_json(self.stats_path(key), [])
        return data if isinstance(data, list) else []

    def get_published_fingerprints(self, key: str) -> set[str]:
        fingerprints: set[str] = set()
        for item in self.get_stats(key):
            value = item.get("fingerprint")
            if value:
                fingerprints.add(str(value))
        return fingerprints

    def get_caption_history(self, key: str) -> list[dict[str, Any]]:
        data = read_json(self.history_path(key), [])
        return data if isinstance(data, list) else []

    def add_caption_history(self, key: str, caption: str) -> None:
        with self._lock:
            history = self.get_caption_history(key)
            history.append({"text": caption.strip(), "timestamp": now_iso()})
            write_json(self.history_path(key), history[-250:])
