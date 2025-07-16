#!/bin/bash

export FLASK_APP=pyfedi.py
flask remove_orphan_files
