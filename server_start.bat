@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Media Autopost Bot Server

if not exist "logs" mkdir "logs"

call setup.bat >> "logs\launcher.log" 2>&1
if errorlevel 1 (
    echo Setup failed. Check logs\launcher.log
    timeout /t 30 /nobreak >nul
    exit /b 1
)

set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

:RUN
echo [%date% %time%] Starting bot >> "logs\launcher.log"
".venv\Scripts\python.exe" -u bot.py
set BOT_EXIT_CODE=%errorlevel%
echo [%date% %time%] Bot stopped with code %BOT_EXIT_CODE%. Restart in 10 seconds. >> "logs\launcher.log"
timeout /t 10 /nobreak >nul
goto RUN
