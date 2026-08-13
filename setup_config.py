from __future__ import annotations

import re
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_EXAMPLE_PATH = BASE_DIR / ".env.example"
ENV_PATH = BASE_DIR / ".env"
TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def valid_token(value: str) -> bool:
    return bool(value and value != "PASTE_BOT_TOKEN_HERE" and TOKEN_RE.fullmatch(value))


def valid_owner_id(value: str) -> bool:
    return value.isdigit() and int(value) > 0


def prompt(label: str) -> str:
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nНалаштування скасовано. / Setup cancelled.")
        raise SystemExit(2)


def replace_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    suffix = "" if text.endswith("\n") else "\n"
    return f"{text}{suffix}{line}\n"


def create_or_update_env(token: str, owner_id: str) -> None:
    if ENV_PATH.exists():
        text = ENV_PATH.read_text(encoding="utf-8-sig")
    elif ENV_EXAMPLE_PATH.exists():
        text = ENV_EXAMPLE_PATH.read_text(encoding="utf-8-sig")
    else:
        text = "BOT_TOKEN=PASTE_BOT_TOKEN_HERE\nOWNER_ID=PASTE_OWNER_ID_HERE\n"
    text = replace_value(text, "BOT_TOKEN", token)
    text = replace_value(text, "OWNER_ID", owner_id)
    ENV_PATH.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    current = read_env(ENV_PATH)
    token = current.get("BOT_TOKEN", "")
    owner_id = current.get("OWNER_ID", "")

    if valid_token(token) and valid_owner_id(owner_id):
        print("Telegram settings: OK / Налаштування Telegram: OK")
        return 0

    print()
    print("========================================")
    print("   First setup / Перше налаштування")
    print("========================================")
    print("Дані зберігаються тільки у локальному файлі .env.")
    print("The values are stored only in the local .env file.")
    print()

    while not valid_token(token):
        token = prompt("Встав BOT_TOKEN від @BotFather: ")
        if not valid_token(token):
            print("[ПОМИЛКА] Токен має неправильний формат. Скопіюй його повністю з @BotFather.")

    while not valid_owner_id(owner_id):
        owner_id = prompt("Введи свій цифровий Telegram OWNER_ID: ")
        if not valid_owner_id(owner_id):
            print("[ПОМИЛКА] OWNER_ID має складатися тільки з цифр. Його можна отримати в @userinfobot.")

    create_or_update_env(token, owner_id)
    print()
    print("[OK] Файл .env налаштовано. / The .env file is configured.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
