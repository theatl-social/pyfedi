#!/usr/bin/env sh
set -e

# This script runs as ROOT and then drops privileges to the 'python' user

export FLASK_APP=pyfedi.py

# 1. Start cron daemon in the background (as root)
echo "Starting cron daemon..."
cron

# 2. Wait for required services
echo "Waiting for PostgreSQL..."
while ! nc -z ${POSTGRES_HOST:-db} ${POSTGRES_PORT:-5432}; do
  sleep 1
done
echo "PostgreSQL is ready!"

echo "Waiting for Redis..."
while ! nc -z ${REDIS_HOST:-redis} ${REDIS_PORT:-6379}; do
  sleep 1
done
echo "Redis is ready!"

# 3. Run setup tasks (as root)
echo "Running database migrations..."
python3 -m flask db upgrade

echo "Populating community search..."
python3 -m flask populate_community_search

# 4. Initialize Redis Streams (create consumer groups if needed)
echo "Initializing Redis Streams..."
python3 -c "
from app import create_app
from app.federation.processor import FederationStreamProcessor
import os

app = create_app()
with app.app_context():
    processor = FederationStreamProcessor(
        redis_url=os.environ.get('REDIS_URL', 'redis://redis:6379/0'),
        database_url=os.environ.get('DATABASE_URL')
    )
    processor.initialize_streams()
    print('Redis Streams initialized successfully')
"

# 5. Drop privileges and run the main application as the 'python' user
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