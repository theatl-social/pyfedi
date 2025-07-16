#!/bin/bash

export FLASK_APP=pyfedi.py
pypy -m flask daily-maintenance-celery
