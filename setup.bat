@echo off
REM ============================================================
REM  Automated Printing System - Windows First-Time Setup
REM  Usage: Double-click setup.bat OR run from Command Prompt
REM  Run once before launching the app for the first time.
REM ============================================================
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Automated Printing System - Setup
echo ============================================================
echo.

REM --- Check Python is installed ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo.
    echo Please download and install Python 3.11 or newer from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: During install, check "Add Python to PATH"
    pause
    exit /b 1
)
echo [OK] Python found:
python --version
echo.

REM --- Create virtual environment ---
if exist ".venv\Scripts\python.exe" (
    echo [OK] Virtual environment already exists. Skipping creation.
) else (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)
echo.

REM --- Upgrade pip ---
echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
echo [OK] pip upgraded.
echo.

REM --- Install dependencies ---
echo Installing dependencies (this may take a few minutes)...
".venv\Scripts\pip.exe" install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.
echo.

REM --- Create data and logs directories ---
if not exist "data" mkdir data
if not exist "logs" mkdir logs
echo [OK] Directories ready.
echo.

echo ============================================================
echo  Setup complete! You can now run the application with:
echo    Double-click run.bat
echo  OR
echo    run.bat  (from Command Prompt)
echo ============================================================
echo.
pause
endlocal
