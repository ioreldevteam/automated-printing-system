@echo off
REM ============================================================
REM  Automated Printing System - Windows Launcher
REM  Usage: Double-click run.bat  OR  run from Command Prompt
REM ============================================================
setlocal
cd /d "%~dp0"

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo.
    echo Please run setup.bat first to install dependencies.
    echo   Double-click setup.bat and follow the instructions.
    echo.
    pause
    exit /b 1
)

REM Create required directories if missing
if not exist "data" mkdir data
if not exist "logs" mkdir logs

REM Launch the application
echo Starting Automated Printing System...
".venv\Scripts\python.exe" -m app.main %*

if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with an error.
    echo Check logs\ folder for details.
    pause
)
endlocal
