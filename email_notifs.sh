#!/bin/bash

source venv/bin/activate
export FLASK_APP=pyfedi.py
python3 -m flask send_missed_notifs
python3 -m flask process_email_bounces
python3 -m flask clean_up_old_activities
