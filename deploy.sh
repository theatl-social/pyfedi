#!/bin/bash

sudo systemctl stop celery.service
sudo systemctl stop pyfedi.service
sudo systemctl stop piefed-notifs.service
git pull
source venv/bin/activate
export FLASK_APP=pyfedi.py
pip install -r requirements.txt
flask db upgrade
pybabel compile -d app/translations
echo "These ^^^^ errors are normal, ignore them."
sudo systemctl start celery.service
sudo systemctl start piefed-notifs.service
sudo systemctl start pyfedi.service
flask populate_community_search

date > updated.txt
