# ActivityPub Request Logging Migration Guide

## Overview
These migrations create database tables and views for tracking ActivityPub POST requests and storing their content for debugging purposes.

## Migration Files Created

1. `20250723_create_ap_request_status.sql` - Creates status tracking table
2. `20250723_create_ap_request_body.sql` - Creates POST body storage table  
3. `20250723_ap_request_logging_complete.sql` - Combined migration (recommended)

## Recommended Execution Order

### Option 1: Use the Combined Migration (RECOMMENDED)
```bash
psql -d your_database -f migrations/20250723_ap_request_logging_complete.sql
```

This single file will:
- Drop any existing ap_request_* objects safely
- Create both tables with proper schema
- Create all indexes for performance
- Create all views for easy querying

### Option 2: Run Individual Migrations
If you prefer to run them separately:

```bash
# 1. Create status tracking table first
psql -d your_database -f migrations/20250723_create_ap_request_status.sql

# 2. Create body storage table second  
psql -d your_database -f migrations/20250723_create_ap_request_body.sql
```

## What Gets Created

### Tables
- `ap_request_status` - Tracks processing checkpoints for each POST
- `ap_request_body` - Stores raw POST content and parsed JSON

### Indexes
- Performance indexes on request_id, activity_id, timestamps
- Optimized for common query patterns

### Views
- `ap_request_status_last` - Latest status for each request
- `ap_request_status_incomplete` - Failed/incomplete requests
- `ap_request_combined` - Joins status and body data
- `ap_request_summary` - High-level overview with activity types

## Safety Features

All migrations include:
- `DROP IF EXISTS` statements to safely remove existing objects
- `CREATE IF NOT EXISTS` where appropriate
- Proper dependency order (views → indexes → tables)
- No impact on existing application tables

## Activation

After running the migration, enable logging with:
```bash
export EXTRA_AP_DB_DEBUG=1
```

## Verification

Check that tables were created:
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_name LIKE 'ap_request_%';
```

Check that views were created:
```sql
SELECT table_name FROM information_schema.views 
WHERE table_name LIKE 'ap_request_%';
```
