# Media Autopost Bot

Повна документація для встановлення, використання та майбутнього передавання покупцю міститься у файлі [`ІНСТРУКЦІЯ.md`](ІНСТРУКЦІЯ.md).

Один Telegram-бот для автопостингу в чотири незалежні канали:

- `HOT_GERLSbot` → профіль `hot_girls`;
- `Hot_puppybot` → профіль `hot_puppy`;
- `Hot_Yaoi_bot` → профіль `hot_yaoi`;
- `Hotboys_media_bot` → профіль `hotboys`.

Кожен профіль має власний `chat_id`, чергу фото/відео, архів, інтервал, мову, футер, набір підписів, статистику, паузу та історію публікацій.

## Що вже перенесено

- `Hot_puppybot`: канал `-1004359012731`, інтервал 30 хв, англійська мова й оригінальний набір підписів `hot_puppy`.
- `Hotboys_media_bot`: канал `@HOT_BOYSES`, інтервал 30 хв, англійська мова й оригінальний набір підписів `hotboys`.
- Для `HOT_GERLSbot` і `Hot_Yaoi_bot` створені профілі, але `chat_id` порожній до перенесення їхніх точних налаштувань.

Усі чотири профілі спочатку стоять на паузі. Це захищає від випадкових або подвійних постів під час переходу.

## В архіві навмисно немає контенту

Папка `channels/` не входить до ZIP. Бот сам створить порожні папки при першому запуску:

```text
channels/
├── hot_girls/photos, videos, archive
├── hot_puppy/photos, videos, archive
├── hot_yaoi/photos, videos, archive
└── hotboys/photos, videos, archive
```

Також у збірці немає старих `.env`, токенів, `venv`, логів, статистики й історії публікацій.

## Перший запуск на Windows Server

Потрібен Python 3.12.

1. Розпакуй проєкт, наприклад у `D:\Bots\Media_Autopost_Bot`.
2. Запусти `start.bat`. Він створить `.venv`, встановить залежності та створить `.env`.
3. Відкрий `.env` і заповни:

```env
BOT_TOKEN=токен_одного_керуючого_бота
OWNER_ID=твій_цифровий_Telegram_ID
```

4. Додай цього одного бота адміністратором усіх каналів із правом публікації.
5. Знову запусти `start.bat` та напиши боту `/start`.

Можна використати токен одного зі старих медіаботів або створити нового через `@BotFather`. Інші старі боти треба зупинити тільки після перевірки нового, інакше вони можуть робити дублікати.

## Перенесення медіа без видалення оригіналів

`import_media.ps1` копіює контент зі старих папок. Передавай шлях саме до папки профілю, всередині якої лежать `photos`, `video`/`videos` та `archive`.

Приклад для двох отриманих ботів:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\import_media.ps1" `
  -HotPuppySource "D:\Bots\Hot_puppybot\channels\hot_Puppy_official" `
  -HotboysSource "D:\Bots\Hotboys_media_bot\channels\HOT_BOYSES"
```

Коли будуть відомі папки двох інших ботів:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\import_media.ps1" `
  -HotGirlsSource "D:\Bots\HOT_GERLSbot\channels\НАЗВА_ПРОФІЛЮ" `
  -HotYaoiSource "D:\Bots\Hot_Yaoi_bot\channels\НАЗВА_ПРОФІЛЮ"
```

Оригінальні файли скрипт не видаляє.

## Налаштування двох каналів без chat_id

У Telegram-боті від імені власника:

```text
/setchat hot_girls -1001234567890
/setchat hot_yaoi -1001234567890
```

Для публічного каналу можна вказати `@username` замість цифрового ID.

## Перевірка перед увімкненням

```text
/status all
/sendnow hot_puppy
/sendnow hotboys
```

Після успішних тестових публікацій:

```text
/resume all
```

## Основні команди

```text
/channels                     — меню чотирьох каналів
/status [key|all]             — стан і кількість медіа
/sendnow [key|all]            — опублікувати зараз
/pause [key|all]              — поставити на паузу
/resume [key|all]             — продовжити
/interval key minutes         — інтервал 1–10080 хв
/language key ua|ru|en        — мова підписів
/upload [key]                 — додавання медіа через Telegram
/upload_stop                  — завершити завантаження
/stats [key]                  — статистика за день і 7 днів
/archive [key]                — кількість файлів в архіві
```

Команди власника:

```text
/setchat key @channel|-100... — змінити канал
/pack key default|hot_puppy|hotboys
/footer key текст|off
/addchannel key chat_id Назва
/delchannel key               — видаляє конфіг, але не контент
/addadmin user_id
/removeadmin user_id
```

## Автозапуск через Планувальник завдань

Запусти PowerShell від адміністратора у папці проєкту:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\install_task.ps1"
```

Буде створене завдання `\TelegramBots\TG_Media_Autopost_Bot`, яке запускає `server_start.bat` від `SYSTEM`. Логи зберігаються у `logs\bot.log` та `logs\launcher.log`.

## Структура коду

```text
start.bat
bot.py
config.py
database.py
handlers/
services/
keyboards/
utils/
app/
.env
requirements.txt
```

Секретний `.env` не завантажуй у GitHub і не надсилай разом із проєктом.
