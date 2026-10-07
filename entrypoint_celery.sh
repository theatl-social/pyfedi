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
# --no-sync is load-bearing, not an optimisation.
#
# The Dockerfile builds /app/.venv with `RUN uv sync` and declares no USER, so
# the venv and its `_editable_impl_pyfedi.pth` are owned by root. Without
# --no-sync, `uv run` re-syncs the editable install at startup and tries to
# remove that file -- which the unprivileged `python` user cannot do:
#
#   error: failed to remove file `/app/.venv/.../_editable_impl_pyfedi.pth`:
#   Permission denied (os error 13)
#
# The web container hides this by accident: entrypoint.sh runs
# `uv run flask db upgrade` as root first, which performs the re-sync, so by
# the time it drops privileges there is nothing left to write. This worker has
# no root-side `uv run`, so the python user is the first to touch the venv.
#
# The image is built with `uv sync --frozen`, so the environment is already
# correct by construction and there is nothing to sync at runtime.
exec gosu python uv run --no-sync celery -A celery_worker_docker.celery worker --concurrency=${CELERY_CONCURRENCY:-4} --queues=celery,background,send
