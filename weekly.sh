#!/bin/bash

export FLASK_APP=pyfedi.py
python3 -m flask remove_orphan_files
