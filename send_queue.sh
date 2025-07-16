#!/bin/bash

export FLASK_APP=pyfedi.py
pypy -m flask send-queue
