@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Media Autopost Bot

call setup.bat
if errorlevel 1 (
    echo.
    echo Setup failed. / Налаштування завершилося помилкою.
    pause
    exit /b 1
)

echo.
echo Starting Media Autopost Bot...
echo Запуск Media Autopost Bot...
echo Press Ctrl+C to stop. / Для зупинки натисни Ctrl+C.
echo.

set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
".venv\Scripts\python.exe" -u bot.py

echo.
echo Bot stopped. Exit code: %errorlevel%
echo Бот зупинено. Код: %errorlevel%
pause
