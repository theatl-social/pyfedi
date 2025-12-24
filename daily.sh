#!/bin/bash

export FLASK_APP=pyfedi.py
uv run flask daily-maintenance
