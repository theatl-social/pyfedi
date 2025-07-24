# PeachPie Fork Differences

This document outlines the key differences between PeachPie (theatl-social fork) and the upstream PyFedi project.

## Overview

PeachPie is a fork of [PyFedi](https://codeberg.org/rimu/pyfedi) maintained by theATL.social community. This fork includes several enhancements focused on debugging, monitoring, and security improvements for ActivityPub federation.

## Major Features Added

### 1. Comprehensive ActivityPub Request Debugging System

A complete request tracking and debugging infrastructure for ActivityPub requests:

- **Dual Logging System**:
  - Database logging via `ap_request_status` and `ap_request_body` tables
  - APRequestLogger class for detailed checkpoint logging
  - Controlled by `ENABLE_AP_REQUEST_LOGGING` and `EXTRA_AP_DB_DEBUG` environment variables

- **Request Body Tracking**:
  - Stores complete POST body content for debugging
  - Tracks request lifecycle from receipt to processing completion
  - Includes content length tracking and parsed JSON storage

- **Admin UI Enhancements**:
  - New admin interface at `/admin/activitypub/ap_requests` for viewing AP request history
  - Combined view showing both request status and body content
  - Detailed error tracking and disposition reasons

### 2. Security Improvements

- **OOM Protection**:
  - Added `MAX_CONTENT_LENGTH` configuration (default 10MB)
  - Single body read with caching to prevent memory exhaustion
  - Early content-length validation with 413 status for oversized requests

- **Input Validation**:
  - Enhanced ID field validation (max 2048 characters)
  - Type checking on critical fields
  - Safe error handling without exposing internal details

- **Bug Fixes**:
  - Fixed AttributeError when accessing `user.id` on None objects
  - Added proper None checks for database query results
  - Fixed scoping issues with redis lock operations

### 3. Enhanced Lemmy Compatibility

- **Improved Announce Processing**:
  - Removed incorrect "Intended for Mastodon" rejection of Lemmy posts
  - More permissive validation for Page/Note objects
  - Better handling of objects without 'object' field

- **Safe Actor Field Access**:
  - Added defensive checks for optional fields
  - Graceful handling of malformed ActivityPub objects

## Branding Changes

- Rebranded from "PieFed" to "PeachPie"
- Footer now links to theATL.social community
- Version string includes "theatl-social" identifier
- Repository links point to GitHub fork instead of Codeberg upstream

## Technical Implementation Details

### Database Schema Additions

```sql
-- Request status tracking
CREATE TABLE ap_request_status (
    request_id VARCHAR(36) PRIMARY KEY,
    step VARCHAR(100),
    status VARCHAR(50),
    activity_id TEXT,
    post_object_uri TEXT,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Request body storage
CREATE TABLE ap_request_body (
    request_id VARCHAR(36) PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    content_length INTEGER,
    body TEXT,
    parsed_json JSONB,
    disposition VARCHAR(255),
    disposition_reason TEXT
);
```

### Configuration Options

New environment variables:
- `ENABLE_AP_REQUEST_LOGGING`: Enable/disable APRequestLogger (default: 1)
- `EXTRA_AP_DB_DEBUG`: Enable/disable database logging (default: 0)
- `MAX_CONTENT_LENGTH`: Maximum request size in bytes (default: 10MB)

### File Structure

Key files added or modified:
- `/app/activitypub/request_logger.py` - APRequestLogger implementation
- `/app/activitypub/request_body_utils.py` - Request body tracking utilities
- `/app/templates/admin/ap_request_status.html` - Admin UI template
- `/docs/activitypub_request_body_tracking.md` - Implementation documentation
- `/migrations/` - SQL migration scripts for new tables

## Upstream Compatibility

This fork maintains compatibility with upstream PyFedi while adding new features. The changes are designed to be:
- Non-breaking to existing functionality
- Configurable via environment variables
- Easily portable back to upstream if desired

## Version

Current version: `1.0.1-20250124-nightly-theatlsocial`

## Contributing

Issues and pull requests should be submitted to: https://github.com/theatl-social/pyfedi

For upstream PyFedi contributions, see: https://codeberg.org/rimu/pyfedi