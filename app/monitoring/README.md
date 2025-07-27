# Federation Monitoring Module

This module provides a web-based monitoring dashboard and API endpoints for tracking the health and performance of the Redis Streams federation system.

## Features

### Dashboard
- Real-time system status overview
- Queue statistics (pending, retry, DLQ)
- Instance health monitoring
- Recent error tracking
- Success rate metrics
- Redis memory usage

### API Endpoints

#### `/monitoring/api/stats`
Returns current system statistics including:
- Queue depths for each priority level
- Activity counts and success rates
- Redis memory usage
- Active consumer counts

#### `/monitoring/api/instances`
Returns health status of federated instances:
- Success rates per instance
- Recent failure counts
- Software and version information
- Last seen timestamps

#### `/monitoring/api/errors`
Returns recent federation errors:
- Error types and messages
- Instance associations
- Retry counts
- Timestamps

#### `/monitoring/api/retry-queue`
Shows items currently in retry queues:
- Activity details
- Scheduled retry times
- Destination instances
- Retry counts

#### `/monitoring/api/dlq`
Shows items in Dead Letter Queues:
- Failed activities
- Error reasons
- Final retry counts

#### `/monitoring/api/memory-status`
Detailed Redis memory statistics:
- Memory usage by data type
- Stream sizes
- Lifecycle management stats

## Access Control

All monitoring endpoints require admin privileges. Non-admin users will receive a 403 Forbidden response.

## Usage

Navigate to `/monitoring/` when logged in as an admin to access the dashboard. The dashboard auto-refreshes every 5 seconds.

## Configuration

No special configuration required. The module uses the existing Redis connection from the application context.

## Development

To add new metrics:
1. Add the data collection logic to the appropriate API endpoint
2. Update the dashboard template to display the new metric
3. Add JavaScript to handle the new data in the auto-refresh cycle