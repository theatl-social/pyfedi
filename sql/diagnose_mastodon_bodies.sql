-- Diagnostic query to check if bodies exist for "Intended for Mastodon" posts
-- This will help determine if the issue is with storage or with the view

-- 1. Find all requests with "Intended for Mastodon" status
SELECT 
    rs.request_id,
    rs.timestamp as status_time,
    rs.details,
    CASE 
        WHEN rb.request_id IS NOT NULL THEN 'Body exists'
        ELSE 'Body missing'
    END as body_status,
    rb.content_length,
    LENGTH(rb.body) as actual_body_length,
    rb.parsed_json->>'type' as activity_type
FROM ap_request_status rs
LEFT JOIN ap_request_body rb ON rs.request_id = rb.request_id
WHERE rs.details = 'Intended for Mastodon'
ORDER BY rs.timestamp DESC
LIMIT 20;

-- 2. Check if these requests have bodies in ap_request_body
SELECT 
    COUNT(*) as total_mastodon_requests,
    COUNT(rb.request_id) as requests_with_body,
    COUNT(*) - COUNT(rb.request_id) as requests_missing_body
FROM ap_request_status rs
LEFT JOIN ap_request_body rb ON rs.request_id = rb.request_id
WHERE rs.details = 'Intended for Mastodon';

-- 3. Show sample of body content for "Intended for Mastodon" posts
SELECT 
    rb.request_id,
    rb.timestamp,
    rb.content_type,
    rb.content_length,
    LEFT(rb.body, 500) as body_preview,
    rb.parsed_json->>'type' as activity_type,
    rb.parsed_json->>'actor' as actor
FROM ap_request_body rb
WHERE rb.request_id IN (
    SELECT request_id 
    FROM ap_request_status 
    WHERE details = 'Intended for Mastodon'
)
LIMIT 5;

-- 4. Check why "Intended for Mastodon" might not appear in summary view
-- The view requires entries in ap_request_body table
SELECT 
    rs.request_id,
    CASE 
        WHEN rb.request_id IS NOT NULL THEN 'Has body record'
        ELSE 'Missing body record - will not appear in ap_request_summary view'
    END as diagnosis,
    rs.timestamp as status_logged,
    rs.checkpoint,
    rs.status,
    rs.details
FROM ap_request_status rs
LEFT JOIN ap_request_body rb ON rs.request_id = rb.request_id
WHERE rs.details = 'Intended for Mastodon'
ORDER BY rs.timestamp DESC
LIMIT 10;