# Alembic Migration Multiple Heads Fix

## Problem Description

The error "Multiple head revisions are present for given argument 'head'" occurs when Alembic detects multiple migration branches that haven't been merged. This happens when:

1. Multiple migrations have the same `down_revision` (creating a fork)
2. Multiple migrations exist without any migrations depending on them (multiple heads)

## Current Issue

As of 2025-01-24, we have:
- **Two heads**: 
  - `01b92d7ec7fb` (ActivityPub tracking tables)
  - `91c80b195029` (default comment sort)
- **One conflict**: Both `01b92d7ec7fb` and `01107dfe5a29` have `down_revision = '755fa58fd603'`

## Resolution Steps

### Option 1: Update Our Migration to Chain After Latest (Recommended)

1. Find the actual latest migration:
   ```bash
   python3 debug_alembic_heads.py
   ```

2. Update our migration to point to the latest head:
   ```python
   # In 01b92d7ec7fb_add_activitypub_request_tracking_tables.py
   revision = '01b92d7ec7fb'
   down_revision = '91c80b195029'  # Changed from '755fa58fd603'
   ```

### Option 2: Create a Merge Migration

1. Run the merge command:
   ```bash
   flask db merge -m "merge heads" 01b92d7ec7fb 91c80b195029
   ```

2. This creates a new migration that depends on both heads, resolving the conflict.

### Option 3: Manual Fix (If Above Fails)

1. Identify the correct chain by checking the database:
   ```sql
   SELECT version_num FROM alembic_version;
   ```

2. Update the migration to depend on whatever version is in the database.

## Testing the Fix

Run the debug script to verify:
```bash
python3 debug_alembic_heads.py
```

You should see:
- "Number of heads: 1"
- No conflicts in down_revisions

Then test the migration:
```bash
flask db upgrade
```

## Prevention

To prevent this in the future:
1. Always check current heads before creating new migrations
2. Use `flask db revision` instead of manually creating migration files
3. Pull latest changes before creating new migrations
4. Run `python3 debug_alembic_heads.py` after creating migrations

## Understanding the Migration Chain

The migration chain should be linear:
```
initial_migration
    ↓
migration_a
    ↓
migration_b
    ↓
migration_c (HEAD)
```

Not branched:
```
migration_a
    ↓
migration_b ← migration_d (creates conflict)
    ↓           ↓
migration_c   migration_e (multiple heads)
```