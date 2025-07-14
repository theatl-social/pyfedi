#!/usr/bin/env sh
set -e

export FLASK_APP=pyfedi.py

echo "Running database migrations..."
flask db upgrade

flask populate_community_search

if [ "${FLASK_DEBUG:-}" = "1" ] && [ "${FLASK_ENV:-}" = "development" ]; then
  export FLASK_RUN_EXTRA_FILES=$(find app/templates app/static -type f | tr '\n' ':')
  echo "Starting flask development server..."
  python3 -m flask run -h 0.0.0.0 -p 5000
else
  echo "Starting Gunicorn..."
  python3 -m gunicorn --config gunicorn.conf.py --preload pyfedi:app
fi
