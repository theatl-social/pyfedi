# Legacy Celery Implementation

⚠️ **WARNING: This code is deprecated and for reference only** ⚠️

This directory contains the old Celery-based task processing system that has been replaced by Redis Streams.

## Why This Code Was Replaced

The Celery implementation had several issues:
- Sporadic task delivery (sometimes minutes, sometimes hours)
- Complex configuration and debugging
- Heavy dependencies
- Connection pool exhaustion issues
- Poor observability

## New System

The new system uses:
- **Redis Streams** for reliable message queuing
- **AsyncIO** for efficient I/O operations
- **Python 3.13** with comprehensive typing
- Simpler architecture with better performance

## Migration Guide

If you're looking to understand how tasks were migrated:

1. Old Celery task: `@celery.task`
2. New Redis Streams task: `@task(name='task_name', priority=Priority.NORMAL)`

3. Old task dispatch: `task.delay()`
4. New task dispatch: Uses `task_selector()` which queues to Redis Streams

## Files in This Directory

- `celery_worker.default.py` - Default Celery worker configuration
- `celery_worker_docker.py` - Docker-specific Celery worker
- `entrypoint_celery.sh` - Docker entrypoint for Celery
- Various task files showing the old implementation

## DO NOT USE THIS CODE

This code is kept only for:
- Historical reference
- Understanding the migration
- Debugging legacy issues

For new development, use the Redis Streams implementation in `/app/federation/`.