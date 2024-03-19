#!/bin/bash
date > updated.txt

sudo systemctl stop celery.service
git pull
source venv/bin/activate
export FLASK_APP=pyfedi.py
flask db upgrade
pybabel compile -d app/translations
sudo systemctl start celery.service
sudo systemctl restart pyfedi.service
