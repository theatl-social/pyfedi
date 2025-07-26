# Dockerfile for PyFedi Security Testing Environment
FROM python:3.11-slim

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

# Copy requirements files
COPY requirements.txt requirements-test.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-test.txt

# Copy test configuration
COPY docker/test/test_config.py ./config/test.py

# Copy entrypoint script
COPY docker/test/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set environment variables
ENV PYTHONPATH=/app
ENV FLASK_APP=app
ENV FLASK_ENV=testing
ENV TESTING=1

# Create directories for test outputs
RUN mkdir -p /app/test-reports /app/coverage-reports

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command runs all security tests
CMD ["security"]