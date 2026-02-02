#!/bin/bash

source venv/bin/activate > /dev/null
export FLASK_APP=pyfedi.py
flask remove_orphan_files
