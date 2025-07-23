-- Migration: Create ap_request_status table for ActivityPub POST debug tracking
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
CREATE INDEX idx_ap_request_status_request_id ON ap_request_status(request_id);
CREATE INDEX idx_ap_request_status_activity_id ON ap_request_status(activity_id);
CREATE INDEX idx_ap_request_status_post_object_uri ON ap_request_status(post_object_uri);

-- View: ap_request_status_last
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

-- View: ap_request_status_incomplete
CREATE OR REPLACE VIEW ap_request_status_incomplete AS
SELECT l.*
FROM ap_request_status_last l
WHERE NOT (l.checkpoint = 'process_inbox_request' AND l.status = 'ok');