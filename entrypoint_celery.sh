#!/usr/bin/env bash
set -e

# This script starts as ROOT so it can fix ownership of the shared cache and
# log directories, then drops to the unprivileged 'python' user, mirroring
# entrypoint.sh. Celery refuses to run as root without an override, and the
# worker has no need for root.

# Ensure directories the worker writes to are owned by the python user.
# CACHE_DIR defaults to /dev/shm/pyfedi and the app logger writes /app/logs.
mkdir -p /dev/shm/pyfedi /app/logs
chown -R python:python /dev/shm/pyfedi /app/logs 2>/dev/null || true

echo "Starting Celery worker as user 'python'..."
# Use 'exec' to replace the shell process with the Celery process
# Use 'gosu' to switch from root to the 'python' user
exec gosu python uv run celery -A celery_worker_docker.celery worker --concurrency=4 --queues=celery,background,send
