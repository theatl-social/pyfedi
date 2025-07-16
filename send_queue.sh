#!/bin/bash

export FLASK_APP=pyfedi.py
flask send-queue
