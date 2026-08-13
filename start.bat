@echo off
setlocal EnableExtensions
title Media Autopost Bot
cd /d "%~dp0"

echo ========================================
echo        Media Autopost Bot
echo ========================================
echo Project: %CD%
echo This window will stay open.
echo.

if not exist "logs" mkdir "logs"
set "STARTUP_LOG=logs\startup_check.log"
echo [%date% %time%] start.bat started > "%STARTUP_LOG%"

call :find_python
if errorlevel 1 goto no_python

echo Python command: %PYTHON_CMD%
echo [%date% %time%] Python command: %PYTHON_CMD% >> "%STARTUP_LOG%"
echo.

call :ensure_dirs

if exist "venv\Scripts\python.exe" (
    call :test_venv
    if errorlevel 1 (
        echo Existing venv is broken or incompatible.
        echo Recreating venv...
        rmdir /s /q "venv" >nul 2>&1
    )
)

if not exist "venv\Scripts\python.exe" (
    if exist "venv" (
        echo Removing incomplete venv...
        rmdir /s /q "venv" >nul 2>&1
    )
    echo Creating venv...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 goto venv_failed
)

call "venv\Scripts\activate.bat"
if errorlevel 1 goto activate_failed

echo.
echo Updating pip tools...
python -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
if errorlevel 1 echo WARNING: pip upgrade failed. Continuing.

echo.
echo Installing requirements...
pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto requirements_failed

echo.
echo Checking Python files...
python -m compileall -q -x "venv|__pycache__" .
if errorlevel 1 goto syntax_failed

echo.
python setup_config.py
if errorlevel 1 goto setup_failed

echo.
echo ========================================
echo Starting bot now...
echo Wait for this line from Python:
echo BOT READY / BOT STARTED
echo ========================================
echo Press Ctrl+C to stop.
echo.

set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
python -u bot.py
set "BOT_EXIT_CODE=%errorlevel%"

echo.
echo ========================================
echo Bot stopped. Exit code: %BOT_EXIT_CODE%
echo Check logs\runtime.log if the exit code is not 0.
echo ========================================
echo.
pause
exit /b %BOT_EXIT_CODE%

:find_python
set "PYTHON_CMD="
call :check_python "py -3.12"
call :check_python "py -3.11"
call :check_python "py -3.10"
call :check_python "python"
call :check_python "python3"
if not defined PYTHON_CMD exit /b 1
exit /b 0

:check_python
if defined PYTHON_CMD exit /b 0
%~1 -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3,10),(3,11),(3,12)] else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=%~1"
exit /b 0

:test_venv
"venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3,10),(3,11),(3,12)] else 1)" >nul 2>&1
exit /b %errorlevel%

:ensure_dirs
if not exist "logs" mkdir "logs"
if not exist "channels" mkdir "channels"
if not exist "data" mkdir "data"
if not exist "stats" mkdir "stats"
if not exist "caption_history" mkdir "caption_history"
exit /b 0

:no_python
echo ERROR: Python 3.10, 3.11 or 3.12 was not found.
echo Install Python 3.12 x64 and enable Add Python to PATH.
goto fail

:venv_failed
echo ERROR: Could not create venv.
echo Try moving the bot to C:\Bots\Media_Autopost_Bot and run again.
goto fail

:activate_failed
echo ERROR: Could not activate venv.
goto fail

:requirements_failed
echo ERROR: Requirements installation failed.
echo Check internet connection and run start.bat again.
goto fail

:syntax_failed
echo ERROR: Python syntax check failed.
goto fail

:setup_failed
echo ERROR: Telegram setup is incomplete.
goto fail

:fail
echo.
echo Startup failed. This window will stay open.
echo Send the text above or logs\startup_check.log if you need help.
echo [%date% %time%] startup failed >> "%STARTUP_LOG%"
echo.
pause
exit /b 1
