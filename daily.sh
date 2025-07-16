#!/bin/bash

export FLASK_APP=pyfedi.py
python3 -m flask daily-maintenance-celery
