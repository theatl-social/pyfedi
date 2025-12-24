# syntax=docker/dockerfile:1.4
FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie AS builder

# Create python user
RUN useradd -m -s /bin/bash python

# Install system dependencies including gosu for privilege dropping
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    gcc \
    python3-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    postgresql-client \
    bash \
    cron \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install Python dependencies using uv (much faster than pip)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY --chown=python:python . /app

WORKDIR /app

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN uv run pybabel compile -d app/translations || true

RUN chmod u+x ./entrypoint.sh
RUN chmod u+x ./entrypoint_celery.sh
RUN chmod u+x ./entrypoint_async.sh

# Run as root so cron daemon can start, then entrypoint.sh will drop to python user via gosu
ENTRYPOINT ["./entrypoint.sh"]
