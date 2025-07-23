-- Check current logging status to understand which system is active

-- 1. Count records in each table
SELECT 
    'ap_request_status' as table_name,
    COUNT(*) as record_count,
    MIN(timestamp) as oldest_record,
    MAX(timestamp) as newest_record
FROM ap_request_status
UNION ALL
SELECT 
    'ap_request_body' as table_name,
    COUNT(*) as record_count,
    MIN(timestamp) as oldest_record,
    MAX(timestamp) as newest_record
FROM ap_request_body;

-- 2. Check if we have status records without corresponding body records
SELECT 
    COUNT(DISTINCT rs.request_id) as total_requests_with_status,
    COUNT(DISTINCT rb.request_id) as total_requests_with_body,
    COUNT(DISTINCT rs.request_id) - COUNT(DISTINCT rb.request_id) as requests_missing_body
FROM ap_request_status rs
LEFT JOIN ap_request_body rb ON rs.request_id = rb.request_id;

-- 3. Recent requests showing the mismatch
SELECT 
    rs.request_id,
    MIN(rs.timestamp) as first_status_logged,
    COUNT(rs.id) as status_entries,
    CASE 
        WHEN rb.request_id IS NOT NULL THEN 'Has body'
        ELSE 'Missing body'
    END as body_status,
    STRING_AGG(DISTINCT rs.checkpoint, ', ' ORDER BY rs.checkpoint) as checkpoints
FROM ap_request_status rs
LEFT JOIN ap_request_body rb ON rs.request_id = rb.request_id
WHERE rs.timestamp > NOW() - INTERVAL '1 hour'
GROUP BY rs.request_id, rb.request_id
ORDER BY MIN(rs.timestamp) DESC
LIMIT 20;

-- 4. Show which logging system created the status records
SELECT 
    rs.checkpoint,
    COUNT(*) as count,
    MIN(rs.timestamp) as earliest,
    MAX(rs.timestamp) as latest
FROM ap_request_status rs
WHERE rs.timestamp > NOW() - INTERVAL '24 hours'
GROUP BY rs.checkpoint
ORDER BY count DESC;