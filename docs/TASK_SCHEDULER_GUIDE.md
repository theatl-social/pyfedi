# Task Scheduler Guide

## Overview

PeachPie includes a powerful task scheduling system that allows you to run recurring and one-time tasks. The scheduler supports:

- **Cron expressions** for complex scheduling patterns
- **Interval-based** scheduling (e.g., every 5 minutes)
- **One-time** scheduled tasks
- **Timezone support** for cron schedules
- **Task persistence** in Redis
- **Admin interface** for managing tasks
- **Automatic retry** on failure

## Architecture

The scheduler consists of three main components:

1. **TaskScheduler**: Core scheduling engine that determines when tasks should run
2. **Task Processors**: Handlers that execute specific task types
3. **Admin Interface**: Web UI for managing scheduled tasks

## Running the Scheduler

The scheduler runs as a separate service alongside your main application:

```bash
# Start the scheduler service
python -m app.scheduler_service

# Or with Docker
docker-compose up scheduler
```

The scheduler service will:
- Connect to Redis and PostgreSQL
- Start the task scheduler
- Start task processors
- Create default maintenance tasks
- Begin checking for tasks to execute

## Task Types

### Maintenance Tasks

Handled by `MaintenanceProcessor`, these tasks perform system maintenance:

- `cleanup_old_activities`: Remove old ActivityPub logs
- `update_instance_stats`: Update instance statistics
- `cleanup_orphaned_data`: Remove orphaned posts/comments
- `purge_deleted_content`: Permanently delete soft-deleted content
- `archive_federation_logs`: Archive old logs to external storage

### Federation Tasks

For scheduled federation activities:
- Retry failed deliveries
- Sync with specific instances
- Batch processing of activities

### Custom Tasks

You can create processors for your own task types.

## Admin Interface

Access the scheduler admin at `/admin/scheduler/scheduled-tasks`.

### Features

1. **Task List**: View all scheduled tasks with status, schedule, and execution info
2. **Create Tasks**: Add new scheduled tasks with various schedule types
3. **Task Details**: View detailed information about specific tasks
4. **Actions**: Pause, resume, run immediately, edit, or delete tasks
5. **Statistics**: View scheduler health and upcoming tasks

### Creating a Task

1. Click "New Task" in the admin interface
2. Fill in:
   - **Name**: Descriptive name for the task
   - **Type**: Which processor handles this task
   - **Schedule Type**: Cron, interval, or one-time
   - **Schedule**: The actual schedule specification
   - **Payload**: JSON data to pass to the processor
   - **Max Retries**: How many times to retry on failure

### Schedule Examples

**Cron Expressions**:
- `0 0 * * *` - Daily at midnight
- `0 2 * * *` - Daily at 2:00 AM
- `0 */4 * * *` - Every 4 hours
- `0 0 * * 0` - Weekly on Sunday
- `*/15 * * * *` - Every 15 minutes

**Intervals**:
- `5m` - Every 5 minutes
- `1h` - Every hour
- `1d` - Every day
- `1w` - Every week

## Creating Custom Task Processors

To handle new task types, create a processor:

```python
# app/tasks/my_processor.py
class MyTaskProcessor:
    def __init__(self, redis_client, async_session_maker):
        self.redis = redis_client
        self.async_session_maker = async_session_maker
        self.stream_name = "stream:my_tasks:tasks"
    
    async def start(self):
        # Create consumer group and start processing
        pass
    
    async def _process_message(self, message_id, data):
        task_name = data.get('task_name')
        payload = data.get('payload', {})
        
        if task_name == 'my_custom_task':
            await self._do_custom_work(payload)
```

Then register it in the scheduler service.

## API Endpoints

### List Tasks
```
GET /admin/scheduler/api/scheduled-tasks
```

### Get Task Details
```
GET /admin/scheduler/api/scheduled-tasks/<task_id>
```

### Create Task
```
POST /admin/scheduler/api/scheduled-tasks
Content-Type: application/json

{
    "name": "my_task",
    "task_type": "maintenance",
    "schedule_type": "cron",
    "schedule": "0 0 * * *",
    "payload": {"key": "value"},
    "timezone": "UTC"
}
```

### Update Task
```
PUT /admin/scheduler/api/scheduled-tasks/<task_id>
```

### Delete Task
```
DELETE /admin/scheduler/api/scheduled-tasks/<task_id>
```

### Pause/Resume Task
```
POST /admin/scheduler/api/scheduled-tasks/<task_id>/pause
POST /admin/scheduler/api/scheduled-tasks/<task_id>/resume
```

### Run Task Immediately
```
POST /admin/scheduler/api/scheduled-tasks/<task_id>/run
```

## Default Tasks

The scheduler creates these default tasks on first run:

1. **cleanup_old_activities**
   - Schedule: Daily at 2 AM
   - Removes ActivityPub logs older than 30 days

2. **update_instance_stats**
   - Schedule: Every hour
   - Updates user and post counts for instances

3. **cleanup_orphaned_data**
   - Schedule: Weekly on Sunday at 3 AM
   - Removes posts/comments from deleted users

4. **purge_deleted_content**
   - Schedule: Daily at 4 AM
   - Permanently removes content deleted > 90 days ago

## Monitoring

### Logs

The scheduler logs all activity:
```
2024-01-15 02:00:00 - Executing scheduled task: cleanup_old_activities
2024-01-15 02:00:05 - Successfully executed task: cleanup_old_activities
```

### Metrics

View scheduler statistics in the admin dashboard:
- Total tasks
- Active/paused/failed tasks
- Upcoming executions
- Recent execution history

### Health Checks

The scheduler exposes health status through the monitoring API.

## Troubleshooting

### Task Not Running

1. Check task status (not paused/failed)
2. Verify schedule is correct
3. Check scheduler service is running
4. Review logs for errors

### Task Failing

1. Check task payload is valid JSON
2. Review processor logs for errors
3. Verify database/Redis connectivity
4. Check error count hasn't exceeded max retries

### High Memory Usage

1. Reduce batch sizes in task payloads
2. Increase interval between executions
3. Archive old data more frequently

## Best Practices

1. **Use Appropriate Schedules**: Don't run heavy tasks too frequently
2. **Set Reasonable Payloads**: Keep task data minimal
3. **Monitor Execution Times**: Adjust schedules based on task duration
4. **Handle Failures Gracefully**: Implement proper error handling in processors
5. **Test Thoroughly**: Test tasks in development before production
6. **Document Tasks**: Use clear, descriptive names and maintain documentation

## Environment Variables

```env
# Scheduler check interval (seconds)
SCHEDULER_CHECK_INTERVAL=60

# Default task retries
SCHEDULER_DEFAULT_RETRIES=3

# Task processor concurrency
SCHEDULER_CONCURRENCY=5
```

## Docker Configuration

Add the scheduler service to your `docker-compose.yml`:

```yaml
scheduler:
  build: .
  command: python -m app.scheduler_service
  environment:
    - DATABASE_URL=${DATABASE_URL}
    - REDIS_URL=${REDIS_URL}
  depends_on:
    - db
    - redis
  restart: unless-stopped
```