@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo       Media Autopost Bot - Setup
echo ========================================

py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.12 not found.
    echo [ПОМИЛКА] Встанови Python 3.12 та увімкни Python Launcher.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv with Python 3.12...
    py -3.12 -m venv .venv
    if errorlevel 1 exit /b 1
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 exit /b 1

if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo.
    echo [ACTION REQUIRED] File .env was created.
    echo [ПОТРІБНА ДІЯ] Відкрий .env та вкажи BOT_TOKEN і OWNER_ID.
)

echo Setup completed.
exit /b 0
