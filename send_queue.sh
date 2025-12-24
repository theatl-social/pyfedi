#!/bin/bash

export FLASK_APP=pyfedi.py
uv run flask send-queue
