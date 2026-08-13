@echo off
setlocal EnableExtensions
title Media Autopost Bot - Setup
cd /d "%~dp0"

echo ========================================
echo        Media Autopost Bot - Setup
echo ========================================
echo This window will stay open.
echo.

call :find_python
if errorlevel 1 goto no_python

echo Python command: %PYTHON_CMD%
echo.

if not exist "logs" mkdir "logs"
if not exist "channels" mkdir "channels"
if not exist "data" mkdir "data"
if not exist "stats" mkdir "stats"
if not exist "caption_history" mkdir "caption_history"

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

python -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto requirements_failed

python -m compileall -q -x "venv|__pycache__" .
if errorlevel 1 goto syntax_failed

python setup_config.py
if errorlevel 1 goto setup_failed

echo.
echo OK: setup completed.
echo.
pause
exit /b 0

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

:no_python
echo ERROR: Python 3.10, 3.11 or 3.12 was not found.
goto fail

:venv_failed
echo ERROR: Could not create venv.
goto fail

:activate_failed
echo ERROR: Could not activate venv.
goto fail

:requirements_failed
echo ERROR: Requirements installation failed.
goto fail

:syntax_failed
echo ERROR: Python syntax check failed.
goto fail

:setup_failed
echo ERROR: Telegram setup is incomplete.
goto fail

:fail
echo.
echo Setup failed. This window will stay open.
echo.
pause
exit /b 1
