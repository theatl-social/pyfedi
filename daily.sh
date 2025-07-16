#!/bin/bash

export FLASK_APP=pyfedi.py
flask daily-maintenance-celery
