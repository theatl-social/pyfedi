#!/usr/bin/env python3
"""
Debug script to analyze alembic migration heads and find conflicts
"""
import os
import re
from collections import defaultdict
from pathlib import Path

def analyze_migrations():
    """Analyze all migration files to find the chain and heads"""
    migrations_dir = Path("migrations/versions")
    
    if not migrations_dir.exists():
        print(f"Error: {migrations_dir} does not exist!")
        return
    
    migrations = {}
    down_revisions = defaultdict(list)
    
    # Read all migration files
    for file_path in migrations_dir.glob("*.py"):
        if file_path.name.startswith("__"):
            continue
            
        with open(file_path, 'r') as f:
            content = f.read()
            
        # Extract revision and down_revision
        rev_match = re.search(r"revision = '([^']+)'", content)
        down_match = re.search(r"down_revision = '([^']+)'", content)
        
        if rev_match:
            revision = rev_match.group(1)
            down_revision = down_match.group(1) if down_match else None
            
            migrations[revision] = {
                'file': file_path.name,
                'down_revision': down_revision,
                'content': content[:200]  # First 200 chars for context
            }
            
            if down_revision:
                down_revisions[down_revision].append(revision)
    
    # Find all heads (revisions that nothing depends on)
    heads = []
    for revision, info in migrations.items():
        if revision not in down_revisions:
            heads.append(revision)
    
    print("=== ALEMBIC MIGRATION ANALYSIS ===\n")
    print(f"Total migrations: {len(migrations)}")
    print(f"Number of heads: {len(heads)}\n")
    
    if len(heads) > 1:
        print("⚠️  MULTIPLE HEADS DETECTED! This is causing the error.\n")
    
    print("Current heads:")
    for head in heads:
        print(f"  - {head} ({migrations[head]['file']})")
        print(f"    down_revision: {migrations[head]['down_revision']}")
    
    # Find conflicting down_revisions
    print("\n=== CONFLICT ANALYSIS ===\n")
    conflicts_found = False
    
    for down_rev, revisions in down_revisions.items():
        if len(revisions) > 1:
            conflicts_found = True
            print(f"⚠️  CONFLICT: Multiple migrations have down_revision = '{down_rev}':")
            for rev in revisions:
                print(f"    - {rev} ({migrations[rev]['file']})")
    
    if not conflicts_found:
        print("No conflicts found in down_revisions.")
    
    # Trace back from heads to find the split point
    print("\n=== MIGRATION CHAINS FROM HEADS ===\n")
    for i, head in enumerate(heads):
        print(f"Chain {i+1} starting from {head}:")
        current = head
        chain = []
        seen = set()
        
        while current and current not in seen:
            seen.add(current)
            info = migrations.get(current, {})
            chain.append(f"  {current} ({info.get('file', 'unknown')})")
            current = info.get('down_revision')
            
            if len(chain) > 10:  # Limit output
                chain.append("  ... (truncated)")
                break
        
        for item in chain:
            print(item)
        print()
    
    # Suggest resolution
    print("=== SUGGESTED RESOLUTION ===\n")
    if len(heads) > 1:
        print("To fix this issue, you need to:")
        print("1. Decide which head should be the true head")
        print("2. Update the other head(s) to depend on the chosen head")
        print("3. Or create a merge migration that depends on all current heads")
        print("\nExample merge migration command:")
        print(f"  flask db merge -m 'merge heads' {' '.join(heads)}")
    else:
        print("No multiple heads detected. The issue might be elsewhere.")

if __name__ == "__main__":
    analyze_migrations()