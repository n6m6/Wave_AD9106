@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Project Python environment not found. Run: python -m venv .venv
    echo Then install pyserial: .venv\Scripts\python.exe -m pip install pyserial
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tools\firing_web.py
if errorlevel 1 pause
