-- SQL Views for ActivityPub Request Body Tracking
-- Run this after the migration to create useful views

-- View: Combined request data with latest status
CREATE OR REPLACE VIEW ap_request_summary AS
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
CREATE OR REPLACE VIEW ap_request_timeline AS
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
CREATE OR REPLACE VIEW ap_failed_requests AS
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
