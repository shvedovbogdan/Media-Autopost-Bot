from __future__ import annotations

import logging
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import (
    ADMINS_PATH,
    BACKUP_ENABLED,
    BACKUP_EVERY_HOURS,
    BACKUP_KEEP_DAYS,
    BACKUPS_DIR,
    BOT_RENTALS_PATH,
    CAPTION_HISTORY_DIR,
    CHANNELS_PATH,
    PAYMENTS_PATH,
    STATS_DIR,
)
from database import JsonDatabase

logger = logging.getLogger("media_autopost.backups")
db = JsonDatabase()


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value))
        return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
    except (TypeError, ValueError):
        return None


def backup_sources() -> list[Path]:
    paths = [CHANNELS_PATH, ADMINS_PATH, BOT_RENTALS_PATH, PAYMENTS_PATH]
    for folder in (STATS_DIR, CAPTION_HISTORY_DIR):
        if folder.exists():
            paths.extend(path for path in folder.rglob("*.json") if path.is_file())
    return [path for path in paths if path.exists()]


def cleanup_old_backups(now: datetime) -> None:
    if not BACKUPS_DIR.exists():
        return
    cutoff = now - timedelta(days=BACKUP_KEEP_DAYS)
    for path in BACKUPS_DIR.glob("media_autopost_backup_*.zip"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified < cutoff:
                path.unlink()
        except OSError:
            logger.exception("Could not remove old backup: %s", path)


def create_backup(now: datetime | None = None) -> Path | None:
    now = now or datetime.now(timezone.utc)
    sources = backup_sources()
    if not sources:
        return None
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    archive = BACKUPS_DIR / f"media_autopost_backup_{now.strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sources:
            zf.write(path, path.relative_to(CHANNELS_PATH.parent).as_posix())
    cleanup_old_backups(now)
    logger.info("Backup created: %s", archive)
    return archive


def maybe_create_backup() -> Path | None:
    if not BACKUP_ENABLED:
        return None
    now = datetime.now(timezone.utc)
    state = db.get_backup_state()
    last_backup = parse_timestamp(state.get("last_backup_at"))
    if last_backup and (now - last_backup).total_seconds() < BACKUP_EVERY_HOURS * 3600:
        return None
    archive = create_backup(now)
    if archive:
        state["last_backup_at"] = now.isoformat()
        state["last_backup_file"] = archive.name
        db.save_backup_state(state)
    return archive
