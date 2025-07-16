#!/bin/bash

export FLASK_APP=pyfedi.py
python3 -m flask send-queue
