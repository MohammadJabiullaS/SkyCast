#!/usr/bin/env bash
# Start the FastAPI weather service (port 8001) and the Django site (port 8000) together.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
.venv/bin/python web/manage.py migrate --noinput >/dev/null

.venv/bin/uvicorn weather_api.main:app --port 8001 --reload --reload-dir weather_api &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

echo "FastAPI docs:  http://127.0.0.1:8001/docs"
echo "SkyCast app:   http://127.0.0.1:8000"
.venv/bin/python web/manage.py runserver 127.0.0.1:8000
