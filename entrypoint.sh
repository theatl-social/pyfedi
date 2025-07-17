#!/usr/bin/env sh
set -e

export FLASK_APP=pyfedi.py

echo "Running database migrations..."
python3 -m flask db upgrade

python3 -m flask populate_community_search

echo "Starting Celery worker and beat..."
celery -A celery_app worker --loglevel=info &
celery -A celery_app beat --loglevel=info &

if [ "${FLASK_DEBUG:-}" = "1" ] && [ "${FLASK_ENV:-}" = "development" ]; then
  export FLASK_RUN_EXTRA_FILES=$(find app/templates app/static -type f | tr '\n' ':')
  echo "Starting flask development server..."
  python3 -m flask run -h 0.0.0.0 -p 5000
else
  echo "Starting Gunicorn..."
  python3 -m gunicorn --config gunicorn.conf.py --preload pyfedi:app
fi