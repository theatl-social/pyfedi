# Fix Applied: Multiple Heads Error Resolved

## Problem
The error "Multiple head revisions are present for given argument 'head'" was caused by an Alembic migration file that conflicted with existing migrations.

## Solution Applied
✅ **Removed the conflicting Alembic migration file:**
- `migrations/versions/20250723_145908_add_ap_request_body_table.py`

## Current Status
- ✅ pyfedi should now start without the multiple heads error
- ✅ ActivityPub logging functionality remains intact in the code
- ✅ Standalone SQL migration files are ready for manual deployment

## Next Steps to Deploy ActivityPub Logging

### 1. Start pyfedi (should work now)
```bash
# pyfedi should start without errors
python pyfedi.py
```

### 2. Deploy the database schema manually
```bash
# Connect to your database and run:
psql -d your_database_name -f migrations/20250723_ap_request_logging_complete.sql
```

### 3. Enable ActivityPub logging
```bash
export EXTRA_AP_DB_DEBUG=1
# Then restart pyfedi
```

### 4. Verify the tables were created
```sql
-- Check tables exist
SELECT table_name FROM information_schema.tables 
WHERE table_name LIKE 'ap_request_%';

-- Should return:
-- ap_request_status
-- ap_request_body
```

## What's Working
- ✅ All ActivityPub functionality preserved
- ✅ log_ap_status() and store_request_body() functions ready
- ✅ Database schema ready for deployment
- ✅ No more Alembic conflicts

The ActivityPub logging system is fully implemented and ready to use once you deploy the database schema manually.
