#!/usr/bin/env python3
"""Remove all Celery imports from the codebase"""
import os
import re

files_to_update = [
    '/Users/michael/code/pyfedi/app/activitypub/routes.py',
    '/Users/michael/code/pyfedi/app/user/utils.py',
    '/Users/michael/code/pyfedi/app/activitypub/util.py',
    '/Users/michael/code/pyfedi/app/activitypub/signature.py',
    '/Users/michael/code/pyfedi/app/community/util.py',
    '/Users/michael/code/pyfedi/app/admin/util.py',
    '/Users/michael/code/pyfedi/app/feed/routes.py',
    '/Users/michael/code/pyfedi/app/community/routes.py',
    '/Users/michael/code/pyfedi/app/user/subscription.py',
    '/Users/michael/code/pyfedi/app/admin/routes.py'
]

for file_path in files_to_update:
    if not os.path.exists(file_path):
        print(f"Skipping {file_path} - does not exist")
        continue
        
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Remove celery from import statements
    # Pattern 1: from app import ..., celery, ...
    content = re.sub(r'(from app import .*?),\s*celery(?=,|\s|$)', r'\1', content)
    # Pattern 2: from app import ..., celery
    content = re.sub(r'(from app import .*?),\s*celery\s*$', r'\1', content, flags=re.MULTILINE)
    # Pattern 3: from app import celery, ...
    content = re.sub(r'from app import celery,\s*', 'from app import ', content)
    # Pattern 4: from app import celery alone
    content = re.sub(r'^from app import celery\s*$', '', content, flags=re.MULTILINE)
    
    # Remove @celery decorators (replace with pass for now)
    content = re.sub(r'@celery\.task\s*\n', '', content)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"Updated {file_path}")

print("Done!")