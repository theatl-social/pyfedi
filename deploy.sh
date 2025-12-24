#!/bin/bash

sudo systemctl stop celery.service
sudo systemctl stop pyfedi.service
sudo systemctl stop piefed-notifs.service
git pull
export FLASK_APP=pyfedi.py
uv sync
uv run flask db upgrade
uv run pybabel compile -d app/translations
echo "These ^^^^ errors are normal, ignore them."
sudo systemctl start celery.service
sudo systemctl start piefed-notifs.service
sudo systemctl start pyfedi.service
uv run flask populate_community_search

date > updated.txt
