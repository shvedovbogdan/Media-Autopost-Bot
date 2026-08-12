from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from config import (
    BASE_DIR,
    DOCUMENT_MEDIA_EXTENSIONS,
    PHOTO_EXTENSIONS,
    VIDEO_EXTENSIONS,
)


def project_path(value: str | Path) -> Path:
    """Resolve paths inside the project. / Перетворює шлях на безпечний абсолютний шлях проєкту."""
    path = Path(value)
    if not path.is_absolute():
        path = BASE_DIR / path
    resolved = path.resolve()
    base = BASE_DIR.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Шлях виходить за межі проєкту: {value}")
    return resolved


def ensure_channel_dirs(channel: dict) -> None:
    paths = channel.get("paths", {})
    for key in ("photos", "videos", "archive"):
        value = paths.get(key)
        if value:
            project_path(value).mkdir(parents=True, exist_ok=True)
    archive = project_path(paths.get("archive", "channels/archive"))
    (archive / "photos").mkdir(parents=True, exist_ok=True)
    (archive / "videos").mkdir(parents=True, exist_ok=True)


def list_files(folder: str | Path, extensions: Iterable[str]) -> list[Path]:
    if not folder:
        return []
    path = project_path(folder)
    if not path.is_dir():
        return []
    allowed = tuple(extension.lower() for extension in extensions)
    return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() in allowed)


def get_media_type_by_suffix(file_name: str) -> str | None:
    suffix = Path(file_name).suffix.lower()
    if suffix in PHOTO_EXTENSIONS:
        return "photo"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in DOCUMENT_MEDIA_EXTENSIONS:
        return "document"
    return None


def unique_path(folder: str | Path, file_name: str) -> Path:
    destination_folder = project_path(folder)
    destination_folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file_name).name
    destination = destination_folder / safe_name
    if not destination.exists():
        return destination
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return destination_folder / f"{destination.stem}_{stamp}{destination.suffix}"
