#!/usr/bin/env python3
"""
Find ALL migration heads, not just those in the connected chain.
"""
import os
import re
from pathlib import Path

def find_all_heads():
    """Find all migration files that are not referenced by other migrations."""
    
    migrations_dir = Path('migrations/versions')
    
    if not migrations_dir.exists():
        print("❌ Migrations directory not found")
        return []
    
    print("🔍 FINDING ALL MIGRATION HEADS")
    print("=" * 40)
    
    # Get all migration files
    migration_files = list(migrations_dir.glob('*.py'))
    print(f"📊 Total migration files: {len(migration_files)}")
    
    # Parse all migrations
    migrations = {}
    all_down_revisions = set()
    
    for file_path in migration_files:
        if file_path.name.startswith('__'):
            continue
            
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Extract revision
            revision_match = re.search(r"revision = ['\"]([^'\"]+)['\"]", content)
            if not revision_match:
                continue
                
            revision = revision_match.group(1)
            
            # Extract down_revision
            down_revision_match = re.search(r"down_revision = ([^\n]+)", content)
            down_revision_raw = down_revision_match.group(1).strip() if down_revision_match else None
            
            migrations[revision] = {
                'file': file_path.name,
                'down_revision_raw': down_revision_raw,
                'content': content
            }
            
            # Parse down_revision to find all dependencies
            if down_revision_raw and down_revision_raw != 'None':
                # Remove quotes and parentheses
                clean_raw = down_revision_raw.strip().strip('\'"()')
                
                if clean_raw and clean_raw != 'None':
                    # Split by comma for tuple format
                    for dep in clean_raw.split(','):
                        dep = dep.strip().strip('\'"')
                        if dep and dep != 'None':
                            all_down_revisions.add(dep)
            
        except Exception as e:
            print(f"⚠️  Error reading {file_path.name}: {e}")
    
    # Find heads (migrations not referenced by others)
    heads = []
    for revision in migrations.keys():
        if revision not in all_down_revisions:
            heads.append(revision)
    
    print(f"\n🎯 Found {len(heads)} migration heads:")
    for i, head in enumerate(sorted(heads)[:20]):  # Show first 20
        print(f"   {i+1:3d}. {head} ({migrations[head]['file']})")
    
    if len(heads) > 20:
        print(f"   ... and {len(heads) - 20} more")
    
    return heads, migrations

if __name__ == '__main__':
    heads, migrations = find_all_heads()
    print(f"\n✅ Complete! Found {len(heads)} orphaned migration heads.")