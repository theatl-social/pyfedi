# ActivityPub Request Status Logging System

## Overview

This system provides comprehensive logging and tracking for incoming ActivityPub requests to help debug silent failures and processing issues in the `/inbox` endpoint.

## Features

- **Complete Request Tracking**: Every incoming POST to `/inbox` is assigned a unique UUID and tracked through all processing phases
- **Detailed Checkpoint Logging**: Each major processing step is logged with status and details
- **Error Capture**: All errors, exceptions, and null/validation failures are captured with stack traces
- **Database Views**: Pre-built SQL views to easily query incomplete or failed requests
- **Admin Interface**: Web interface to browse failed requests and view detailed processing timelines
- **Safe Logging**: Logging failures won't crash the main processing - system continues even if logging fails

## Database Schema

The system uses a single table `ap_request_status` with the following structure:

```sql
CREATE TABLE ap_request_status (
    id SERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT now(),
    checkpoint VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    activity_id TEXT,
    post_object_uri TEXT,
    details TEXT
);
```

### Key Views

- **`ap_request_status_last`**: Shows the latest status for each request
- **`ap_request_status_incomplete`**: Shows requests that haven't completed successfully

## Setup/Installation

### 1. Run Database Migration

First, create the required database table and views:

```bash
# Using psql command line
psql -d your_database_name -f migrations/20250723_create_ap_request_status.sql

# Or using your preferred database administration tool
# Execute the SQL contents of migrations/20250723_create_ap_request_status.sql
```

### 2. Enable Logging

Set the environment variable to enable the logging system:

```bash
# Add to your environment (e.g., .env file, systemd service, docker-compose, etc.)
ENABLE_AP_REQUEST_LOGGING=1
```

**Options:**
- `ENABLE_AP_REQUEST_LOGGING=1` - Enable comprehensive AP request logging
- `ENABLE_AP_REQUEST_LOGGING=0` or unset - Disable logging (default)

### 3. Restart Application

After running the migration and setting the environment variable, restart your PieFed application. The logging system will automatically activate and begin tracking all incoming ActivityPub requests to `/inbox`.

**Performance Note:** When disabled (`ENABLE_AP_REQUEST_LOGGING=0` or unset), the logging system has virtually zero performance impact - all logging calls return immediately without doing any work.

## Usage

### Automatic Logging

Once the database migration is applied, the environment variable is set to `ENABLE_AP_REQUEST_LOGGING=1`, and the application is restarted, the system automatically logs all incoming ActivityPub requests. Every POST to `/inbox`, `/u/{actor}/inbox`, `/c/{actor}/inbox`, and `/site_inbox` will be tracked with comprehensive checkpoint logging.

When logging is disabled (`ENABLE_AP_REQUEST_LOGGING=0` or unset), all logging operations are skipped immediately with minimal performance overhead.

### Viewing Logs

#### Admin Web Interface

1. Navigate to `/admin/ap_requests` (admin only)
2. View list of incomplete/failed requests
3. Click "View Full" to see detailed processing timeline
4. Check `/admin/ap_stats` for 24-hour statistics

#### Database Queries

**Find all incomplete requests:**
```sql
SELECT * FROM ap_request_status_incomplete ORDER BY timestamp DESC;
```

**Trace a specific request:**
```sql
SELECT * FROM ap_request_status 
WHERE request_id = 'your-request-uuid-here' 
ORDER BY timestamp ASC;
```

**Find requests with errors:**
```sql
SELECT DISTINCT request_id, activity_id, details
FROM ap_request_status 
WHERE status = 'error' 
ORDER BY timestamp DESC;
```

**Get completion rate for last 24 hours:**
```sql
WITH completed AS (
    SELECT COUNT(DISTINCT request_id) as count
    FROM ap_request_status
    WHERE checkpoint = 'process_inbox_request' 
    AND status = 'ok'
    AND timestamp > NOW() - INTERVAL '24 hours'
),
total AS (
    SELECT COUNT(DISTINCT request_id) as count
    FROM ap_request_status
    WHERE checkpoint = 'initial_receipt'
    AND timestamp > NOW() - INTERVAL '24 hours'
)
SELECT 
    completed.count as completed,
    total.count as total,
    ROUND((completed.count::float / total.count) * 100, 2) as completion_rate
FROM completed, total;
```

## Checkpoint Reference

The system logs the following checkpoints in order:

1. **`initial_receipt`** - Request first received
2. **`json_parse`** - JSON parsing attempt
3. **`request_info_extracted`** - Activity ID and object URI extracted
4. **`site_loaded`** - Site configuration loaded
5. **`field_validation`** - Required fields validated
6. **`announce_processing`** - Announce activity processing (if applicable)
7. **`duplicate_check`** - Redis duplicate check
8. **`peertube_filter`** - PeerTube activity filtering
9. **`account_deletion_check`** - Account deletion processing
10. **`actor_lookup`** - Actor lookup/creation
11. **`actor_validation`** - Actor validation
12. **`signature_verify_start`** - Starting signature verification
13. **`signature_verify`** - HTTP signature verification
14. **`ld_signature_verify`** - LD signature verification (fallback)
15. **`instance_update`** - Instance information update
16. **`main_processing_dispatch`** - Dispatch to main processing
17. **`process_inbox_request_start`** - Main processing task started
18. **`process_inbox_request`** - Main processing completed

### Status Values

- **`ok`** - Step completed successfully
- **`error`** - Step failed with an error
- **`warning`** - Step had issues but continued
- **`ignored`** - Step was skipped/ignored (e.g., duplicate requests)

## Debugging Silent Failures

### Common Issues to Look For

1. **Requests stuck at early checkpoints**: Check for JSON parsing errors or missing required fields
2. **Signature verification failures**: Look for `signature_verify` errors
3. **Actor lookup failures**: Check `actor_lookup` and `actor_validation` steps
4. **Processing never starts**: Look for requests that reach `main_processing_dispatch` but never start `process_inbox_request_start`
5. **Tasks hanging**: Requests that start `process_inbox_request_start` but never complete

### Investigation Steps

1. **Check incomplete requests view:**
   ```sql
   SELECT * FROM ap_request_status_incomplete 
   ORDER BY timestamp DESC LIMIT 50;
   ```

2. **Find error patterns:**
   ```sql
   SELECT checkpoint, details, COUNT(*) as count
   FROM ap_request_status 
   WHERE status = 'error' 
   AND timestamp > NOW() - INTERVAL '24 hours'
   GROUP BY checkpoint, details
   ORDER BY count DESC;
   ```

3. **Trace specific problematic activity:**
   ```sql
   SELECT * FROM ap_request_status 
   WHERE activity_id = 'https://example.com/activities/123'
   ORDER BY timestamp ASC;
   ```

## Performance Considerations

- Logging uses raw SQL to minimize overhead
- Failed logging attempts are caught and don't interrupt processing
- Database indexes are provided on key columns for efficient querying
- Old logs should be periodically cleaned up (consider adding a cleanup job)

## Cleanup Recommendations

Consider running periodic cleanup to prevent the table from growing too large:

```sql
-- Delete successful requests older than 7 days
DELETE FROM ap_request_status 
WHERE timestamp < NOW() - INTERVAL '7 days'
AND request_id IN (
    SELECT request_id FROM ap_request_status
    WHERE checkpoint = 'process_inbox_request' AND status = 'ok'
);

-- Keep failed/incomplete requests longer (30 days)
DELETE FROM ap_request_status 
WHERE timestamp < NOW() - INTERVAL '30 days'
AND request_id NOT IN (
    SELECT request_id FROM ap_request_status_incomplete
);
```

## File Structure

- `app/activitypub/request_logger.py` - Main logging classes and functions
- `app/activitypub/admin_views.py` - Admin web interface routes
- `app/templates/admin/ap_request_status.html` - Admin interface template
- `app/models.py` - APRequestStatus model added
- `migrations/20250723_create_ap_request_status.sql` - Database migration
