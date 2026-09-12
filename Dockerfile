# syntax=docker/dockerfile:1.4
FROM python:3.13-slim-trixie AS builder

# Create python user
RUN useradd -m -s /bin/bash python

# Install system dependencies including gosu for privilege dropping
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    gcc \
    python3-dev \
    libpq-dev \
    curl \
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

EXPOSE 5000
ENV CRON="false"

LABEL org.opencontainers.image.authors="PeachPie"
LABEL org.opencontainers.image.source="https://github.com/theatl-social/pyfedi"
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later"
LABEL org.opencontainers.image.description="A Lemmy/Mbin alternative written in Python with Flask. PeachPie is a fork of PieFed (https://codeberg.org/rimu/pyfedi)."

HEALTHCHECK --interval=60s --retries=2 --timeout=10s CMD curl -ILfSs http://localhost:5000/health >/dev/null || exit 1

# Run as root so cron daemon can start, then entrypoint.sh will drop to python user via gosu
ENTRYPOINT ["./entrypoint.sh"]
