# Test Fixing Methodology

This document outlines the systematic approach for fixing test failures in PyFedi/PeachPie, particularly when dealing with model-database schema mismatches.

## Overview

When the test suite was initially broken (0% passing, 217+ errors), we identified that the primary issues were systemic rather than individual test failures. This required a methodical approach to identify and fix root causes.

## Key Principles

### 1. **Identify Systemic Issues First**
Instead of fixing tests one by one, look for patterns that affect multiple tests:
- Common import errors
- Fixture conflicts
- Model-database mismatches
- Missing test infrastructure

### 2. **Fix Root Causes, Not Symptoms**
When you see an error like "column X doesn't exist", the solution depends on analysis:
- **If the column is used in code**: Add a migration (the feature exists but database is missing it)
- **If the column is unused**: Remove from model (it was added speculatively but never implemented)
- **If the column name is wrong**: Rename to match existing code usage

### 3. **Preserve Existing Functionality**
The codebase has been in production. When models differ from the database:
- The database schema (via migrations) is the source of truth
- The original models.py file shows what actually exists
- New typed models may have added speculative features

## Step-by-Step Methodology

### Step 1: Assess the Damage
```bash
# Run tests to see the full scope of failures
docker-compose run --rm test-runner python -m pytest -x
```

### Step 2: Categorize Errors
Group errors by type:
1. **Import Errors** - Missing modules, circular imports
2. **Fixture Errors** - Duplicate fixtures, scope mismatches  
3. **Schema Errors** - Model doesn't match database
4. **Infrastructure** - Missing test setup (e.g., g.site)

### Step 3: Fix in Order of Impact
1. **Import errors first** - Nothing works if imports fail
2. **Fixture conflicts** - Tests can't even start
3. **Infrastructure setup** - Required for tests to run
4. **Schema mismatches** - Fix systematically by model

### Step 4: Schema Mismatch Resolution

When encountering "column X does not exist":

1. **Check if column is used in code**:
   ```bash
   grep -r "\.column_name" app/
   ```

2. **Check if column exists in original model**:
   ```bash
   grep "column_name" legacy/models/models_original.py
   ```

3. **Check if column has a migration**:
   ```bash
   grep -r "column_name" migrations/
   ```

4. **Make decision**:
   - Used in code + useful feature → Create migration
   - Not used anywhere → Remove from model
   - Wrong name → Rename to match code/database

### Step 5: Create Migrations When Needed

For new useful features (like User.suspended for permission management):

```python
"""Add description of what this adds

Revision ID: timestamp
Revises: previous_migration_id
Create Date: YYYY-MM-DD HH:MM:SS

"""
from alembic import op
import sqlalchemy as sa

revision = 'timestamp'
down_revision = 'previous_id'

def upgrade():
    with op.batch_alter_table('table_name', schema=None) as batch_op:
        batch_op.add_column(sa.Column('column_name', sa.Type(), nullable=True))
    
    # Set defaults for existing rows
    op.execute('UPDATE "table" SET column = default WHERE column IS NULL')
    
    # Make not nullable after setting defaults
    with op.batch_alter_table('table_name', schema=None) as batch_op:
        batch_op.alter_column('column_name',
                              existing_type=sa.Type(),
                              nullable=False)

def downgrade():
    with op.batch_alter_table('table_name', schema=None) as batch_op:
        batch_op.drop_column('column_name')
```

### Step 6: Test Iteratively

After each fix:
1. Rebuild Docker image (if model changes)
2. Run specific test to verify fix
3. Check for new errors
4. Document what was fixed

## Common Patterns We've Found

### 1. Model Drift
The typed models (app/models/*.py) were created from the original monolithic models.py but included:
- Speculative new features that were never implemented
- Different column names than the database
- Missing columns that exist in the database

### 2. Naming Inconsistencies
- `registration_open` (model) vs `registration_mode` (database)
- `hide_read_content` (model) vs `hide_read_posts` (code/database)
- `reply_count` (model) vs `post_reply_count` (database)
- `registered_at` (model) vs `created` (database)

### 3. Missing Infrastructure
Tests expected certain infrastructure that wasn't set up:
- `g.site` object not initialized
- Database keys not generated
- Test fixtures at wrong scope level

## Results Tracking

Track progress systematically:
1. Initial state: X errors, Y% passing
2. After each systemic fix: New error count and %
3. Document each pattern found and fixed
4. Keep a running list of what's left to fix

## Key Learnings

1. **Always check actual usage** before adding migrations
2. **Database schema is source of truth** for existing systems
3. **Fix systemic issues before individual tests**
4. **Document patterns** to help fix similar issues faster
5. **Preserve existing functionality** - don't break production features

## Tools and Commands

### Useful Investigation Commands
```bash
# Find where a column is used
grep -r "\.column_name" app/ --include="*.py"

# Check if column exists in migrations  
grep -r "column_name" migrations/

# Find all model classes
grep "class.*db.Model" app/models/*.py

# Check original model structure
grep -A 20 "class ModelName" legacy/models/models_original.py

# Count test failures by type
pytest --tb=short | grep -E "ERROR|FAILED" | sort | uniq -c
```

### Docker Commands for Testing
```bash
# Rebuild after model changes
docker-compose build test-runner

# Run specific test
docker-compose run --rm test-runner python -m pytest path/to/test.py::test_name -xvs

# Run all tests with stop on first failure
docker-compose run --rm test-runner python -m pytest -x
```

## Current Status Tracking

When fixing tests, maintain a status like:

```
Fixed:
- ✅ Site model alignment (all columns match database)
- ✅ User.suspended migration (used for permissions)
- ✅ Datetime imports (34 files)
- ✅ Fixture conflicts (12 test files)

In Progress:
- 🔄 User model remaining columns
- 🔄 Other model validations

Remaining:
- ❓ Unknown until current fixes are complete
```

This methodology has taken us from 0% to 16.5% passing tests by fixing systemic issues rather than individual test failures.