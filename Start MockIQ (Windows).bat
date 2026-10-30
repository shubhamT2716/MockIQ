@echo off
title MockIQ - AI Interview Platform
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer from https://www.python.org
  echo and tick "Add Python to PATH" during installation. Then run this file again.
  pause
  exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo MockIQ needs Python 3.11 or newer. Your version:
  python --version
  pause
  exit /b 1
)

if not exist ".venv" (
  echo First run: setting up. This takes a minute or two...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo Installing dependencies failed. Check your internet connection and try again.
  pause
  exit /b 1
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo Created your settings file .env and opened it in Notepad.
  echo Paste your Anthropic API key, save, close Notepad, then run this file again.
  echo No key yet? Change LLM_PROVIDER=anthropic to LLM_PROVIDER=fake to try the app.
  notepad ".env"
  pause
  exit /b 0
)

echo.
echo MockIQ is starting. Your browser will open at http://localhost:8000
echo Keep this window open while you practise. Close it to stop MockIQ.
echo.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
python -m uvicorn app.main:create_app --factory --port 8000
pause
