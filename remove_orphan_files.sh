#!/bin/bash

export FLASK_APP=pyfedi.py
pypy -m flask remove_orphan_files
