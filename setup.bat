@echo off
title JARVIS OS Setup & Dependency Verification
echo ============================================================
echo           JARVIS OS 3.0 — Automated Setup Script
echo ============================================================
echo.

:: 1. Verify Python Installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo [OK] Python detected.

:: 2. Create Virtual Environment
if not exist "venv" (
    echo [INFO] Creating Python virtual environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
)
echo [OK] Virtual environment ready.

:: 3. Install Dependencies
echo [INFO] Installing required Python packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Some dependencies failed to install. Continuing...
)

:: 4. Generate .env file if missing
if not exist ".env" (
    echo [INFO] Generating .env configuration from template...
    copy .env.example .env >nul
)
echo [OK] Configuration file (.env) ready.

:: 5. Create Required Directories
if not exist "Screenshots" mkdir Screenshots
if not exist "CalendarEvents" mkdir CalendarEvents
if not exist "Backups" mkdir Backups

:: 6. Verify Ollama Installation
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Ollama is not installed or not running!
    echo LLM planning will fallback to local fast-routing.
    echo To enable full conversational AI, install Ollama from: https://ollama.com/
) else (
    echo [OK] Ollama detected.
)

echo.
echo ============================================================
echo [SUCCESS] JARVIS setup complete!
echo.
echo To start JARVIS OS:
echo   Run: run.bat
echo ============================================================
pause
