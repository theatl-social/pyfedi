#!/usr/bin/env sh
set -e

# This script now runs as ROOT

export FLASK_APP=pyfedi.py

# 1. Start cron daemon in the background (as root)
echo "Starting cron daemon..."
cron

# 2. Ensure directories are writable by python user
mkdir -p /dev/shm/pyfedi /app/logs
chown -R python:python /dev/shm/pyfedi /app/logs 2>/dev/null || true

# 3. Run setup tasks (as root)
# Skip migrations for SQLite (used in testing)
if echo "$DATABASE_URL" | grep -q "^sqlite"; then
  echo "Skipping database migrations (SQLite testing mode)"
else
  echo "Running database migrations..."
  python3 -m flask db upgrade
fi

# echo "Populating community search..."
# python3 -m flask populate_community_search

# 3. Drop privileges and run the main application as the 'python' user
if [ "${FLASK_DEBUG:-}" = "1" ] && [ "${FLASK_ENV:-}" = "development" ]; then
  export FLASK_RUN_EXTRA_FILES=$(find app/templates app/static -type f | tr '\n' ':')
  echo "Starting flask development server as user 'python'..."
  # Use 'exec' to replace the shell process with the Flask process
  # Use 'gosu' to switch from root to the 'python' user
  exec gosu python python3 -m flask run -h 0.0.0.0 -p 5000
else
  echo "Starting Gunicorn as user 'python'..."
  # Use 'exec' to replace the shell process with the Gunicorn process
  # Use 'gosu' to switch from root to the 'python' user
  exec gosu python python3 -m gunicorn --config gunicorn.conf.py --preload pyfedi:app
fi