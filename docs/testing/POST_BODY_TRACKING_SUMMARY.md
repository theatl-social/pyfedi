# ActivityPub POST Body Tracking - Implementation Summary

## What We've Added

### 1. New Database Table: `ap_request_body`
- Stores complete POST request content and metadata
- Links to existing `ap_request_status` table via `request_id`
- Fields include:
  - `headers`: Request headers (sensitive ones filtered out)
  - `body`: Raw POST body content
  - `parsed_json`: Parsed JSON if successful
  - `content_type`, `content_length`: Request metadata
  - `remote_addr`, `user_agent`: Client information

### 2. Enhanced Request Logger
- Added `store_request_body()` method to `APRequestLogger` class
- Automatically stores POST content during request processing
- Handles both successful JSON parsing and parse failures
- Filters sensitive headers (authorization, cookies, etc.)

### 3. Database Migration
- Migration file: `20250723_145908_add_ap_request_body_table.py`
- Creates table with proper indexes and constraints
- Ready to run with: `flask db upgrade`

### 4. SQL Views for Analysis
- `ap_request_summary`: Combined view of requests with latest status
- `ap_request_timeline`: Processing timeline for each request  
- `ap_failed_requests`: Failed requests with full context
- SQL file: `sql/ap_request_views.sql`

### 5. Debug Web Interface
- `/activitypub/debug/ap_requests` - Overview dashboard
- `/activitypub/debug/ap_request/<id>` - Detailed request view
- Shows processing timeline, headers, raw body, parsed JSON
- Admin-only access for security

### 6. Utility Functions
- `app/activitypub/request_body_utils.py` - Query helpers
- Functions for retrieving recent requests, failed requests, statistics
- Used by debug interface and available for custom queries

## Integration Points

### In `shared_inbox()` function:
```python
# After JSON parsing
if logger:
    logger.store_request_body(request, request_json)

# Even on parse failure  
if logger:
    logger.store_request_body(request, None)
```

### Environment Variable Control:
```bash
ENABLE_AP_REQUEST_LOGGING=1  # Enables both status tracking AND body storage
```

## Usage Examples

### View recent requests:
Visit: `/activitypub/debug/ap_requests`

### Query failed requests:
```sql
SELECT * FROM ap_failed_requests 
WHERE received_at > NOW() - INTERVAL '1 hour';
```

### Find requests by actor:
```sql
SELECT request_id, activity_type, raw_post_body 
FROM ap_request_summary 
WHERE actor LIKE '%suspicious-domain.com%';
```

### Performance analysis:
```sql
SELECT activity_type, COUNT(*), AVG(checkpoint_count)
FROM ap_request_summary
GROUP BY activity_type;
```

## Security & Privacy

- Sensitive headers automatically filtered out
- Admin-only access to debug interface
- Consider data retention policies for large POST bodies
- IP addresses logged for debugging (consider privacy implications)
- Raw bodies may contain sensitive data - secure database access appropriately

## Next Steps

1. Run the migration: `flask db upgrade`
2. Create the SQL views: `psql -f sql/ap_request_views.sql`
3. Set `ENABLE_AP_REQUEST_LOGGING=1`
4. Test with incoming ActivityPub requests
5. Monitor disk usage as POST bodies accumulate
6. Consider adding data retention policies

This gives you complete visibility into what ActivityPub requests are being received, how they're processed, and the ability to inspect the full content for debugging and analysis.
