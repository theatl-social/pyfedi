# syntax=docker/dockerfile:1.4
FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie AS builder

# Create python user
RUN useradd -m -s /bin/bash python

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    gcc \
    python3-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    postgresql-client \
    bash \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=source=requirements.txt,target=/tmp/requirements.txt \
    pip3 install -r /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install gunicorn

COPY --chown=python:python . /app

WORKDIR /app

RUN pybabel compile -d app/translations || true

RUN chmod u+x ./entrypoint.sh
RUN chmod u+x ./entrypoint_celery.sh
RUN chmod u+x ./entrypoint_async.sh

USER python
ENTRYPOINT ["./entrypoint.sh"]
