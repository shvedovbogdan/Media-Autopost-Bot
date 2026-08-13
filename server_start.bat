@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

:START
echo ==================================================
echo [%date% %time%] Starting Media_Autopost_Bot
echo ================================================== >> "logs\bot.log"
echo [%date% %time%] Starting Media_Autopost_Bot >> "logs\bot.log"

if not exist "venv\Scripts\python.exe" (
    echo ERROR: venv not found. Run start.bat first.
    echo [%date% %time%] ERROR: venv not found. Run start.bat first. >> "logs\bot.log"
    timeout /t 30 /nobreak >nul
    goto START
)

"venv\Scripts\python.exe" -u "bot.py" >> "logs\bot.log" 2>&1

echo [%date% %time%] Bot stopped. Restarting in 10 seconds... >> "logs\bot.log"
echo Bot stopped. Restarting in 10 seconds...
timeout /t 10 /nobreak >nul
goto START
