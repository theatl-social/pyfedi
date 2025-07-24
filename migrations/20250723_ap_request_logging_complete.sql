-- Combined Migration: Create ActivityPub request logging tables
-- This creates both tables needed for AP POST tracking and body storage

-- Drop existing objects if they exist (safe cleanup)
-- Views first (they depend on tables)
DROP VIEW IF EXISTS ap_request_summary;
DROP VIEW IF EXISTS ap_request_combined;
DROP VIEW IF EXISTS ap_request_status_incomplete;
DROP VIEW IF EXISTS ap_request_status_last;

-- Indexes next (they depend on tables)
DROP INDEX IF EXISTS idx_ap_request_body_remote_addr;
DROP INDEX IF EXISTS idx_ap_request_body_timestamp;
DROP INDEX IF EXISTS idx_ap_request_body_request_id;
DROP INDEX IF EXISTS idx_ap_request_status_timestamp;
DROP INDEX IF EXISTS idx_ap_request_status_post_object_uri;
DROP INDEX IF EXISTS idx_ap_request_status_activity_id;
DROP INDEX IF EXISTS idx_ap_request_status_request_id;

-- Tables last
DROP TABLE IF EXISTS ap_request_body;
DROP TABLE IF EXISTS ap_request_status;

-- Table 1: ap_request_status - tracks processing checkpoints
CREATE TABLE IF NOT EXISTS ap_request_status (
    id SERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT now(),
    checkpoint VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    activity_id TEXT,
    post_object_uri TEXT,
    details TEXT
);

-- Indexes for ap_request_status
CREATE INDEX IF NOT EXISTS idx_ap_request_status_request_id ON ap_request_status(request_id);
CREATE INDEX IF NOT EXISTS idx_ap_request_status_activity_id ON ap_request_status(activity_id);
CREATE INDEX IF NOT EXISTS idx_ap_request_status_post_object_uri ON ap_request_status(post_object_uri);
CREATE INDEX IF NOT EXISTS idx_ap_request_status_timestamp ON ap_request_status(timestamp);

-- Table 2: ap_request_body - stores POST content
CREATE TABLE IF NOT EXISTS ap_request_body (
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

-- Indexes for ap_request_body
CREATE INDEX IF NOT EXISTS idx_ap_request_body_request_id ON ap_request_body(request_id);
CREATE INDEX IF NOT EXISTS idx_ap_request_body_timestamp ON ap_request_body(timestamp);
CREATE INDEX IF NOT EXISTS idx_ap_request_body_remote_addr ON ap_request_body(remote_addr);

-- Views for easier querying
CREATE OR REPLACE VIEW ap_request_status_last AS
SELECT DISTINCT ON (request_id)
    id,
    request_id,
    timestamp,
    checkpoint,
    status,
    activity_id,
    post_object_uri,
    details
FROM ap_request_status
ORDER BY request_id, timestamp DESC;

CREATE OR REPLACE VIEW ap_request_status_incomplete AS
SELECT l.*
FROM ap_request_status_last l
WHERE NOT (l.checkpoint = 'process_inbox_request' AND l.status = 'ok');

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
    END as activity_type,
    CASE 
        WHEN b.parsed_json IS NOT NULL THEN b.parsed_json->>'actor'
        ELSE NULL 
    END as actor
FROM ap_request_status s
LEFT JOIN ap_request_body b ON s.request_id = b.request_id
ORDER BY s.request_id, s.timestamp DESC;
