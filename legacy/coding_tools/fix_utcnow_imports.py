#!/usr/bin/env python3
"""Fix utcnow imports across the codebase"""
import os
import re

# Files that need fixing based on TESTING_PLAN.md
files_to_fix = [
    'app/chat/util.py',
    'app/auth/util.py',
    'app/auth/passkeys.py',
    'app/auth/oauth_util.py',
    'app/admin/routes.py',
    'app/user/utils.py',
    'app/user/routes.py',
    'app/shared/auth.py',
    'app/topic/routes.py',
    'app/api/alpha/utils/post.py',
    'app/dev/routes.py',
    'app/activitypub/request_logger.py',
    'app/activitypub/routes/api.py',
    'app/activitypub/routes/actors.py',
    'app/community/util.py',
    'app/community/forms.py',
    'app/main/routes.py'
]

def fix_utcnow_import(filepath):
    """Fix utcnow import in a single file"""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Pattern to match various import styles
    patterns = [
        # from app.models import ..., utcnow, ...
        (r'(from app\.models import [^\n]*?)(,\s*utcnow)(,\s*[^\n]*)', r'\1\3'),
        # from app.models import utcnow, ...
        (r'from app\.models import utcnow,\s*([^\n]+)', r'from app.models import \1'),
        # from app.models import ..., utcnow (at end)
        (r'from app\.models import ([^\n]+?),\s*utcnow\s*$', r'from app.models import \1'),
        # from app.models import utcnow (only import)
        (r'^from app\.models import utcnow\s*$', r''),
    ]
    
    # Apply patterns
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    # Clean up any double commas or trailing commas
    content = re.sub(r',\s*,', ',', content)
    content = re.sub(r'from app\.models import\s*\n', '', content)
    
    # Check if we need to add the utils import
    if 'utcnow' in original_content and 'from app.utils import utcnow' not in content:
        # Find where to insert the import
        lines = content.split('\n')
        insert_idx = 0
        
        # Find the last import line
        for i, line in enumerate(lines):
            if line.startswith('from app.') or line.startswith('import '):
                insert_idx = i + 1
        
        # Insert the new import
        lines.insert(insert_idx, 'from app.utils import utcnow')
        content = '\n'.join(lines)
    
    # Only write if content changed
    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Fixed: {filepath}")
        return True
    else:
        print(f"No changes needed: {filepath}")
        return False

def main():
    fixed_count = 0
    for filepath in files_to_fix:
        if fix_utcnow_import(filepath):
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")

if __name__ == '__main__':
    main()