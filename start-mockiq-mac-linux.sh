#!/usr/bin/env bash
# MockIQ - AI Interview Platform: one-step start for macOS and Linux.
set -e
cd "$(dirname "$0")"

PY=python3
command -v $PY >/dev/null 2>&1 || { echo "Python 3.11+ is required. Install it from https://www.python.org"; exit 1; }
$PY -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "MockIQ needs Python 3.11 or newer (you have $($PY --version))."; exit 1; }

if [ ! -d .venv ]; then
  echo "First run: setting up. This takes a minute or two..."
  $PY -m venv .venv
fi
source .venv/bin/activate
python -m pip install --disable-pip-version-check -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Created your settings file: $(pwd)/.env"
  echo "Open it, paste your Anthropic API key, save, then run this script again."
  echo "No key yet? Set LLM_PROVIDER=fake to try the app."
  exit 0
fi

echo
echo "MockIQ is starting at http://localhost:8000  (press Ctrl+C to stop)"
( sleep 4; (command -v open >/dev/null && open http://localhost:8000) || (command -v xdg-open >/dev/null && xdg-open http://localhost:8000) || true ) &
exec python -m uvicorn app.main:create_app --factory --port 8000
