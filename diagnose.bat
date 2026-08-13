@echo off
setlocal EnableExtensions
title Media Autopost Bot - Diagnostics
cd /d "%~dp0"

echo ========================================
echo        Media Autopost Bot - Diagnostics
echo ========================================
echo This window will stay open.
echo.

if not exist "venv\Scripts\python.exe" (
    echo ERROR: venv not found. Run start.bat first.
    echo.
    pause
    exit /b 1
)

set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
"venv\Scripts\python.exe" -u diagnose.py
set "DIAG_EXIT_CODE=%errorlevel%"

echo.
if "%DIAG_EXIT_CODE%"=="0" (
    echo OK: diagnostics completed successfully.
) else (
    echo ERROR: diagnostics found a problem.
)
echo.
pause
exit /b %DIAG_EXIT_CODE%
