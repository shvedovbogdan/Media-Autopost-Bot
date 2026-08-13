@echo off
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

set PYTHONUNBUFFERED=1

:START

echo ================================================== >> "logs\bot.log"
echo [%date% %time%] Starting Media_Autopost_Bot >> "logs\bot.log"

"venv\Scripts\python.exe" -u "bot.py" >> "logs\bot.log" 2>&1

echo [%date% %time%] Bot stopped. Restarting in 10 seconds... >> "logs\bot.log"

timeout /t 10 /nobreak >nul

goto START
