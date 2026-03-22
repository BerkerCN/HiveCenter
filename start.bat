@echo off
title HiveCenter AGI Engine
echo =========================================================
echo    HiveCenter (The Omniscience AGI) Windows Starter
echo =========================================================

:: 1. Virtual Environment & Requirements
echo [INFO] Setting up Python Virtual Environment...
if not exist "venv\" (
    python -m venv venv
)

:: Activate VENV
call venv\Scripts\activate.bat

echo [INFO] Installing dependencies...
python -m pip install -q -r requirements.txt

:: 2. Create generic workspace directory
if not exist "workspace\" mkdir workspace

:: 3. Playwright browser check (Optional Visual Engine setup)
python -m playwright help >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing Web Vision (Chromium)...
    python -m playwright install chromium
)

:: 4. Boot up the server
echo [INFO] Booting Neural Network Engine and Dashboard...
start "Hive Server (DO NOT CLOSE)" python hive_app.py

echo.
echo =========================================================
echo [SUCCESS] System is LIVE!
echo Do not close this CMD window while Hive is running.
echo =========================================================
pause
