# Request ID Consistency Report

## Summary
After reviewing the code, the request_id consistency has been fixed with the following changes:

### Fixed Issues:
1. **Dual request_id generation**: The main issue was that two different UUIDs were being generated:
   - One by the main inbox handler at line 771
   - Another by APRequestLogger's constructor at line 30 of request_logger.py

2. **Background task propagation**: When background tasks received a request_id, they correctly reused it, but when they didn't have one, they would generate a new one without propagating it back.

### Changes Made:

1. **In routes.py line 780**: Added `logger.request_id = request_id` to ensure APRequestLogger uses the same request_id as the standalone logging functions.

2. **In routes.py line 805**: Added `logger.store_request_body(request, request_json)` to ensure the APRequestLogger also stores the request body when enabled.

3. **In routes.py lines 1129-1130 and 2046-2047**: Added code to capture the request_id from newly created loggers in background tasks.

### Request ID Flow:

1. **Main inbox endpoint** (/inbox):
   - Generates ONE request_id at line 771
   - Uses it for both standalone functions and APRequestLogger
   - Passes it to background tasks

2. **Background tasks** (process_inbox_request, process_delete_request):
   - If request_id provided: reuses it consistently
   - If no request_id: creates new logger and captures its request_id

3. **All error paths**: Use the same request_id throughout

### Result:
- All APRequestStatus records will have matching APRequestBody records
- "Intended for Mastodon" posts will now appear in the ap_request_summary view
- Both logging systems (standalone and APRequestLogger) use the same request_id