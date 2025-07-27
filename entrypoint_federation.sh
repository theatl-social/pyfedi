#!/usr/bin/env sh
set -e

# Federation worker entrypoint script for Redis Streams processor

echo "Starting PyFedi Federation Worker..."

# Wait for Redis to be ready
echo "Waiting for Redis..."
while ! nc -z ${REDIS_HOST:-redis} ${REDIS_PORT:-6379}; do
  sleep 1
done
echo "Redis is ready!"

# Wait for database to be ready
echo "Waiting for PostgreSQL..."
while ! nc -z ${POSTGRES_HOST:-db} ${POSTGRES_PORT:-5432}; do
  sleep 1
done
echo "PostgreSQL is ready!"

# Set Python path
export PYTHONPATH=/app:$PYTHONPATH

# Start the federation processor
echo "Starting Federation Stream Processor..."
exec python3 -m app.federation.processor