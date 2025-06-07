#!/usr/bin/env sh

echo "Running configuration check..."
export FLASK_APP=pyfedi.py
flask config_check

echo "Running database migrations..."
flask db upgrade

pybabel compile -d app/translations
echo "These ^^^^ errors are normal, ignore them."

flask populate_community_search

echo "Starting Gunicorn..."
gunicorn --config gunicorn.conf.py --preload pyfedi:app
