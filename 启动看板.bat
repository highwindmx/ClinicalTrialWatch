@echo off
chcp 936 >nul 2>&1
title Clinical Dashboard

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Python venv not found. Please run setup.bat first.
    pause
    exit /b 1
)

echo Starting Clinical Trial Dashboard...
echo URL: http://localhost:5000
echo Press Ctrl+C to stop.
echo.

start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5000"

venv\Scripts\python.exe app.py

pause
