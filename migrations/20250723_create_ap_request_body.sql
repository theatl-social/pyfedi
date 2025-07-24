-- Migration: Create ap_request_body table for storing ActivityPub POST content

-- Drop existing objects if they exist (safe cleanup)
DROP VIEW IF EXISTS ap_request_summary;
DROP VIEW IF EXISTS ap_request_combined;
DROP INDEX IF EXISTS idx_ap_request_body_remote_addr;
DROP INDEX IF EXISTS idx_ap_request_body_timestamp;
DROP INDEX IF EXISTS idx_ap_request_body_request_id;
DROP TABLE IF EXISTS ap_request_body;

-- Create the table
CREATE TABLE ap_request_body (
    id SERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT now(),
    headers JSONB,
    body TEXT NOT NULL,
    parsed_json JSONB,
    content_type VARCHAR(128),
    content_length INTEGER,
    remote_addr VARCHAR(45),
    user_agent TEXT
);

-- Create indexes
CREATE INDEX idx_ap_request_body_request_id ON ap_request_body(request_id);
CREATE INDEX idx_ap_request_body_timestamp ON ap_request_body(timestamp);
CREATE INDEX idx_ap_request_body_remote_addr ON ap_request_body(remote_addr);

-- View: ap_request_combined
-- Combines status tracking with request body for easy debugging
CREATE OR REPLACE VIEW ap_request_combined AS
SELECT 
    s.request_id,
    s.timestamp as status_timestamp,
    s.checkpoint,
    s.status,
    s.activity_id,
    s.post_object_uri,
    s.details,
    b.timestamp as body_timestamp,
    b.headers,
    b.body,
    b.parsed_json,
    b.content_type,
    b.content_length,
    b.remote_addr,
    b.user_agent
FROM ap_request_status s
LEFT JOIN ap_request_body b ON s.request_id = b.request_id
ORDER BY s.timestamp DESC;

-- View: ap_request_summary
-- Shows latest status for each request with body info
CREATE OR REPLACE VIEW ap_request_summary AS
SELECT DISTINCT ON (s.request_id)
    s.request_id,
    s.timestamp as last_status_time,
    s.checkpoint as last_checkpoint,
    s.status as last_status,
    s.activity_id,
    s.post_object_uri,
    b.remote_addr,
    b.content_type,
    b.content_length,
    CASE 
        WHEN b.parsed_json IS NOT NULL THEN b.parsed_json->>'type'
        ELSE NULL 
    END as activity_type
FROM ap_request_status s
LEFT JOIN ap_request_body b ON s.request_id = b.request_id
ORDER BY s.request_id, s.timestamp DESC;
