#!/bin/sh

uv run celery --app celery_worker_docker.celery worker --autoscale=5,1 --queues=celery,background,send
