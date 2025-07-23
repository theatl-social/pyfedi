# ActivityPub Request Body Tracking - SQL Views and Queries

## Database Schema

### Tables
- `ap_request_status` - Tracks processing checkpoints for each request
- `ap_request_body` - Stores the actual POST content and headers

### Useful SQL Views

```sql
-- View: Combined request data with latest status
CREATE VIEW ap_request_summary AS
SELECT 
    rb.request_id,
    rb.timestamp as received_at,
    rb.remote_addr,
    rb.user_agent,
    rb.content_type,
    rb.content_length,
    rb.parsed_json->>'type' as activity_type,
    rb.parsed_json->>'actor' as actor,
    rb.parsed_json->>'id' as activity_id,
    CASE 
        WHEN rb.parsed_json->>'object' IS NOT NULL 
        AND rb.parsed_json->'object'->>'id' IS NOT NULL 
        THEN rb.parsed_json->'object'->>'id'
        ELSE rb.parsed_json->>'object'
    END as post_object_uri,
    (SELECT status.status 
     FROM ap_request_status status 
     WHERE status.request_id = rb.request_id 
     ORDER BY status.timestamp DESC 
     LIMIT 1) as latest_status,
    (SELECT status.checkpoint 
     FROM ap_request_status status 
     WHERE status.request_id = rb.request_id 
     ORDER BY status.timestamp DESC 
     LIMIT 1) as latest_checkpoint,
    (SELECT COUNT(*) 
     FROM ap_request_status status 
     WHERE status.request_id = rb.request_id) as checkpoint_count,
    (SELECT COUNT(*) 
     FROM ap_request_status status 
     WHERE status.request_id = rb.request_id 
     AND status.status = 'error') as error_count
FROM ap_request_body rb;

-- View: Request processing timeline
CREATE VIEW ap_request_timeline AS
SELECT 
    rs.request_id,
    rb.timestamp as received_at,
    rb.parsed_json->>'type' as activity_type,
    rb.parsed_json->>'actor' as actor,
    rs.checkpoint,
    rs.status,
    rs.timestamp as checkpoint_time,
    rs.details,
    EXTRACT(EPOCH FROM (rs.timestamp - rb.timestamp)) * 1000 as processing_time_ms
FROM ap_request_status rs
JOIN ap_request_body rb ON rs.request_id = rb.request_id
ORDER BY rb.timestamp DESC, rs.timestamp ASC;

-- View: Failed requests with full context
CREATE VIEW ap_failed_requests AS
SELECT 
    rb.request_id,
    rb.timestamp as received_at,
    rb.remote_addr,
    rb.parsed_json->>'type' as activity_type,
    rb.parsed_json->>'actor' as actor,
    rb.parsed_json->>'id' as activity_id,
    rb.body as raw_post_body,
    rb.headers,
    array_agg(
        json_build_object(
            'checkpoint', rs.checkpoint,
            'status', rs.status,
            'timestamp', rs.timestamp,
            'details', rs.details
        ) ORDER BY rs.timestamp
    ) as processing_steps
FROM ap_request_body rb
JOIN ap_request_status rs ON rb.request_id = rs.request_id
WHERE EXISTS (
    SELECT 1 FROM ap_request_status rs2 
    WHERE rs2.request_id = rb.request_id 
    AND rs2.status = 'error'
)
GROUP BY rb.request_id, rb.timestamp, rb.remote_addr, rb.parsed_json, rb.body, rb.headers
ORDER BY rb.timestamp DESC;
```

## Useful Queries

### Recent requests overview
```sql
SELECT * FROM ap_request_summary 
ORDER BY received_at DESC 
LIMIT 50;
```

### Requests by activity type
```sql
SELECT 
    activity_type,
    COUNT(*) as total_requests,
    COUNT(CASE WHEN latest_status = 'error' THEN 1 END) as failed_requests,
    AVG(checkpoint_count) as avg_checkpoints
FROM ap_request_summary 
WHERE received_at > NOW() - INTERVAL '24 hours'
GROUP BY activity_type
ORDER BY total_requests DESC;
```

### Processing timeline for a specific request
```sql
SELECT * FROM ap_request_timeline 
WHERE request_id = 'YOUR_REQUEST_ID_HERE'
ORDER BY checkpoint_time;
```

### Find requests from specific actor
```sql
SELECT 
    request_id,
    received_at,
    activity_type,
    latest_status,
    latest_checkpoint
FROM ap_request_summary 
WHERE actor LIKE '%example.com%'
ORDER BY received_at DESC;
```

### Slow processing requests
```sql
SELECT 
    request_id,
    received_at,
    activity_type,
    actor,
    checkpoint_count,
    latest_status
FROM ap_request_summary
WHERE checkpoint_count > 10
ORDER BY received_at DESC;
```

### Failed requests with full POST body
```sql
SELECT 
    request_id,
    received_at,
    activity_type,
    actor,
    raw_post_body,
    processing_steps
FROM ap_failed_requests
WHERE received_at > NOW() - INTERVAL '1 hour'
ORDER BY received_at DESC;
```

### Performance metrics
```sql
-- Average processing time by activity type
SELECT 
    rb.parsed_json->>'type' as activity_type,
    COUNT(*) as request_count,
    AVG(EXTRACT(EPOCH FROM (
        (SELECT MAX(timestamp) FROM ap_request_status rs WHERE rs.request_id = rb.request_id) - 
        rb.timestamp
    )) * 1000) as avg_processing_time_ms
FROM ap_request_body rb
WHERE rb.timestamp > NOW() - INTERVAL '24 hours'
GROUP BY rb.parsed_json->>'type'
ORDER BY avg_processing_time_ms DESC;
```

## Environment Variables

Enable request body logging by setting:
```bash
ENABLE_AP_REQUEST_LOGGING=1
```

This will activate both the checkpoint tracking and POST body storage.

## Debug Web Interface

When logged in as an admin, you can access debug information via:

- `/activitypub/debug/ap_requests` - Overview of recent requests and statistics
- `/activitypub/debug/ap_request/<request_id>` - Detailed view of a specific request

These endpoints show:
- Processing timeline with all checkpoints
- Request headers and metadata  
- Raw POST body content
- Parsed JSON structure
- Error details if processing failed

## Storage Considerations

- POST bodies can be large, monitor disk usage
- Consider adding data retention policies
- Headers are filtered to exclude sensitive data (authorization, cookies, etc.)
- JSON parsing errors are handled gracefully - raw body is still stored

## Security Notes

- Sensitive headers are automatically excluded from storage
- Raw POST bodies may contain sensitive data - secure access appropriately  
- Consider encrypting stored bodies for additional security
- IP addresses are logged for debugging but consider privacy implications
