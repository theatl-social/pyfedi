#!/bin/bash

source venv/bin/activate > /dev/null 2>&1
export FLASK_APP=pyfedi.py
flask remove_orphan_files
