#!/bin/bash

export FLASK_APP=pyfedi.py
uv run flask remove_orphan_files
