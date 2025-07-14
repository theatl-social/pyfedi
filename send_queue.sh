#!/bin/bash

source venv/bin/activate
export FLASK_APP=pyfedi.py
python3 -m flask send-queue
