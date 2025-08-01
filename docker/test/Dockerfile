# Dockerfile for PyFedi Security Testing Environment
FROM python:3.13-bookworm

# Build arguments
ARG TESTING=1
ARG FLASK_ENV=testing

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    postgresql-client \
    redis-tools \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements files first (for better caching)
COPY requirements.txt requirements-test.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-test.txt && \
    pip install --no-cache-dir gunicorn celery

# Copy application files
COPY app ./app
COPY tests ./tests
COPY migrations ./migrations
COPY scripts ./scripts
COPY pyfedi.py ./
COPY config.py ./
# Celery no longer used - replaced with Redis Streams

# Copy test configuration
COPY docker/test/test_env.py ./
COPY docker/test/test_config.py ./config/test.py
COPY docker/test/init_test_db_custom.py ./docker/test/

# Copy and set up entrypoint script
COPY docker/test/test-entrypoint.sh /test-entrypoint.sh
RUN chmod +x /test-entrypoint.sh

# Create required .env file (even if empty)
RUN touch .env

# Set environment variables
ENV PYTHONPATH=/app
ENV FLASK_APP=pyfedi.py
ENV FLASK_ENV=testing
ENV TESTING=1

# Create directories for test outputs
RUN mkdir -p /app/test-reports /app/coverage-reports /app/logs

# Set entrypoint
ENTRYPOINT ["/test-entrypoint.sh"]