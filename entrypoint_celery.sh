#!/bin/sh

python3 -m celery -A celery_worker_docker.celery worker --autoscale=5,1 --queues=celery,background,send

