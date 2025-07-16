#!/bin/bash


export FLASK_APP=pyfedi.py
pypy -m flask send_missed_notifs
pypy -m flask process_email_bounces
pypy -m flask clean_up_old_activities
