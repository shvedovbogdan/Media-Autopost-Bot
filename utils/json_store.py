from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

_write_lock = threading.RLock()


def read_json(path: Path, default: Any) -> Any:
    """Read JSON safely. / Безпечно читає JSON."""
    if not path.exists():
        return deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return deepcopy(default)


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically. / Атомарно записує JSON без ризику часткового файлу."""
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        tmp_path.replace(path)

