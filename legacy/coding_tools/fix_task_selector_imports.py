#!/usr/bin/env python3
"""Fix task_selector imports"""
import os

files_to_fix = [
    'app/post/routes.py',
    'app/auth/util.py',
    'app/auth/oauth_util.py',
    'app/auth/routes.py',
    'app/admin/routes.py',
    'app/shared/community.py',
    'app/shared/reply.py',
    'app/cli.py',
    'app/api/alpha/utils/community.py',
    'app/community/routes.py'
]

for filepath in files_to_fix:
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            content = f.read()
        
        new_content = content.replace(
            'from app.shared.tasks import task_selector',
            'from app.federation.tasks import task_selector'
        )
        
        if new_content != content:
            with open(filepath, 'w') as f:
                f.write(new_content)
            print(f"Fixed: {filepath}")
        else:
            print(f"No changes needed: {filepath}")