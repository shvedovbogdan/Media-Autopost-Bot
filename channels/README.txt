ПАПКА ДЛЯ КОНТЕНТУ / CONTENT FOLDER
===================================

Це коренева папка черг усіх каналів.
Не перейменовуйте та не видаляйте її.

Покупець сам додає потрібну кількість каналів командою:

    /addchannel key @channel Назва каналу

Якщо користувач не є owner, перед додаванням каналів він має оплатити оренду:

    /rentbot

Після цього бот автоматично створить:

    channels\key\photos
    channels\key\videos
    channels\key\archive\photos
    channels\key\archive\videos

Фото додавайте в photos, відео — у videos.
Файли також можна завантажувати прямо через Telegram командою /upload key.

This is the root folder for all channel queues. Each /addchannel command
creates separate photos, videos, and archive folders automatically.
