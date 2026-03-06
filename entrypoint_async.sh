#!/usr/bin/env sh
set -e

echo "Starting async server..."

if [ "${FLASK_DEBUG:-}" = "1" ] && [ "${FLASK_ENV:-}" = "development" ]; then
  uv run uvicorn fastapi_server:app --reload --host 0.0.0.0 --port 8000
else
  echo "Starting Uvicorn..."
  uv run uvicorn fastapi_server:app --host 0.0.0.0 --port 8000
fi
