#!/usr/bin/env python3
"""
Diagnostic script to check ActivityPub request body logging
Run this to troubleshoot why bodies aren't being stored in ap_request_body table
"""

import os
import sys

print("=== ActivityPub Request Body Logging Diagnostics ===\n")

# Check environment variable
extra_ap_db_debug = os.environ.get('EXTRA_AP_DB_DEBUG', '0')
print(f"1. Environment Variable Check:")
print(f"   EXTRA_AP_DB_DEBUG = '{extra_ap_db_debug}'")
print(f"   Logging enabled: {extra_ap_db_debug == '1'}")

if extra_ap_db_debug != '1':
    print("\n❌ ISSUE FOUND: EXTRA_AP_DB_DEBUG is not set to '1'")
    print("   Solution: Set the environment variable:")
    print("   export EXTRA_AP_DB_DEBUG=1")
    print("   Then restart pyfedi")
else:
    print("   ✅ Environment variable is correctly set")

print(f"\n2. Database Table Check:")
try:
    # Try to connect to database and check tables
    print("   Checking if ap_request_body table exists...")
    # This would require database connection, which we can't do here
    print("   (Database connection test would require running pyfedi environment)")
    
    print(f"\n3. Model Import Check:")
    sys.path.append('.')
    try:
        from app.models import APRequestBody, APRequestStatus
        print("   ✅ APRequestStatus model imported successfully")
        print("   ✅ APRequestBody model imported successfully")
    except ImportError as e:
        print(f"   ❌ Model import failed: {e}")
        
    print(f"\n4. Function Call Check:")
    with open('app/activitypub/routes.py', 'r') as f:
        content = f.read()
    
    store_calls = content.count('store_request_body(')
    print(f"   Found {store_calls} calls to store_request_body()")
    
    if 'store_request_body(request_id, request)' in content:
        print("   ✅ Initial body storage call found")
    else:
        print("   ❌ Initial body storage call missing")
        
    if 'store_request_body(request_id, request, request_json)' in content:
        print("   ✅ JSON body update call found")
    else:
        print("   ❌ JSON body update call missing")

except Exception as e:
    print(f"   ❌ Error during checks: {e}")

print(f"\n=== TROUBLESHOOTING STEPS ===")
print("1. Make sure EXTRA_AP_DB_DEBUG=1 is set in your environment")
print("2. Run the database migration:")
print("   psql -d your_database -f migrations/20250723_ap_request_logging_complete.sql")
print("3. Restart pyfedi after setting the environment variable")
print("4. Check pyfedi logs for [APRequestBody-DB-FAIL] messages")
print("5. Verify tables exist with: SELECT * FROM ap_request_body LIMIT 1;")
