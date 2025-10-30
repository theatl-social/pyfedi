# Migration Guide - Fix code_style Column Error

## Issue

After merging upstream/main, you may see this error:

```
ERROR in startup_validation: (psycopg2.errors.UndefinedColumn) column user.code_style does not exist
LINE 1: ...password_updated_at AS user_password_updated_at, "user".cod...
```

## Root Cause

The `code_style` column was added in upstream migration `25ac2012570d_add_code_style_option.py` but your production database hasn't run the migrations yet.

## Migration Path

The merge introduced these upstream migrations that need to be applied:

1. `25ac2012570d` - Add code_style option (adds `user.code_style` column)
2. `1b0b1a3f63b1` - Community default post type
3. `f9a75d6851c9` - Index slug
4. `2411d5c6539e` - Remove slug index
5. `461c871f0f58` - User file association
6. `merge_20251029` - Merge migration heads (combines our changes + upstream)

## Solution

### Step 1: Stop Your Services

```bash
docker compose down
```

### Step 2: Backup Your Database

**CRITICAL: Always backup before running migrations!**

```bash
# For Docker PostgreSQL
docker compose exec postgres pg_dump -U pyfedi pyfedi > backup-$(date +%Y%m%d-%H%M%S).sql

# Or if using external PostgreSQL
pg_dump -U your_user -h your_host pyfedi > backup-$(date +%Y%m%d-%H%M%S).sql
```

### Step 3: Run Migrations

```bash
# Pull latest code
git pull origin main

# Run migrations
docker compose run --rm web flask db upgrade

# OR if running locally:
# source .venv/bin/activate
# SERVER_NAME=localhost flask db upgrade
```

### Step 4: Verify Migrations

```bash
# Check that all migrations are applied
docker compose run --rm web flask db current

# Should show: merge_20251029 (head)
```

### Step 5: Restart Services

```bash
docker compose up -d
```

### Step 6: Verify No Errors

```bash
# Check logs for the startup_validation error
docker compose logs web | grep "code_style"
docker compose logs celery | grep "code_style"

# Should see no errors
```

## Prevention

The new test `tests/test_model_column_existence.py` will catch missing columns in CI:

```bash
# Run the test locally
SERVER_NAME=localhost python -m pytest tests/test_model_column_existence.py -v
```

This test verifies that all model columns actually exist in the database schema.

## Rollback (If Needed)

If you encounter issues and need to rollback:

```bash
# Stop services
docker compose down

# Restore from backup
docker compose exec postgres psql -U pyfedi pyfedi < backup-TIMESTAMP.sql

# Or for external PostgreSQL
psql -U your_user -h your_host pyfedi < backup-TIMESTAMP.sql

# Restart
docker compose up -d
```

## Migration Details

The `code_style` column is used to store user preferences for code syntax highlighting style. Default value is "fruity".

**Model definition** ([app/models.py:1220](app/models.py#L1220)):
```python
code_style = db.Column(db.String(25), default="fruity")
```

**Migration** ([migrations/versions/25ac2012570d_add_code_style_option.py](migrations/versions/25ac2012570d_add_code_style_option.py)):
```python
def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('code_style', sa.String(length=25), nullable=True))
```
