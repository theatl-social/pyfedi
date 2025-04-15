#!/bin/bash

sudo systemctl stop celery.service
git pull
source venv/bin/activate
export FLASK_APP=pyfedi.py
pip install -r requirements.txt
flask db upgrade
pybabel compile -d app/translations
sudo systemctl start celery.service
sudo systemctl restart pyfedi.service
flask populate_community_search

date > updated.txt
