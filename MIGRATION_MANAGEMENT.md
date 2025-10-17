# Database Migration Management Guide

## 🎯 Overview

This guide covers how to manage Alembic database migrations when working with a fork that has custom migrations diverging from upstream.

## ⚠️ The Problem

When both your fork and upstream add new migrations, merging upstream creates **multiple migration heads**. This breaks deployments with the error:
```
alembic.util.exc.CommandError: Multiple head revisions are present
```

## 🔍 Understanding Migration Heads

### What are Migration Heads?
- Each migration has a **revision ID** and references a **down_revision** (parent)
- A **head** is a migration with no children - the latest in a branch
- Alembic expects a single linear history with one head

### Why Multiple Heads Occur
```
Your Fork:          A → B → C → D (your custom migration)
                          ↘
Upstream:           A → B → C → E (upstream's new migration)

After merge:        A → B → C → D (head 1)
                              ↘
                                E (head 2)
```

## 📋 Step-by-Step Resolution

### 1. Detect Multiple Heads
```bash
# Check current heads
source .venv/bin/activate
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads
```

Output with multiple heads:
```
349e99c9b2ef (head)
fb3a5a7696f7 (head)
```

### 2. Create Merge Migration
```bash
# Merge the heads
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db merge <head1> <head2> -m "merge migration heads"

# Example:
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db merge 349e99c9b2ef fb3a5a7696f7 -m "merge migration heads after upstream merge"
```

### 3. Verify Single Head
```bash
# Should now show only one head
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads
```

### 4. Test Migration
```bash
# Test upgrade works
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db upgrade

# Run migration tests
SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_migration_heads.py -v
```

## 🚨 Common Scenarios

### Scenario 1: After Merging Upstream
**When**: You've just merged upstream/main
**Action**:
```bash
# 1. Fetch and merge upstream
git fetch upstream main
git merge upstream/main

# 2. Check for migration conflicts
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads

# 3. If multiple heads, create merge migration
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db merge <head1> <head2> -m "merge upstream migrations"

# 4. Commit the merge migration
git add migrations/versions/*.py
git commit -m "Merge migration heads after upstream sync"
```

### Scenario 2: Before Creating PR
**When**: Preparing a PR after local development
**Action**:
```bash
# Run the migration check
./check-pr.sh  # Uses our PR checklist script

# If heads conflict detected, resolve before pushing
```

### Scenario 3: CI/CD Failure
**When**: GitHub Actions fails with migration head error
**Action**:
```bash
# 1. Pull latest changes
git pull origin <your-branch>

# 2. Create merge migration locally
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db merge <head1> <head2> -m "fix CI migration heads"

# 3. Push fix
git add migrations/
git commit -m "Fix migration heads for CI/CD"
git push origin <your-branch>
```

## 🛠️ Automated Helper Script

Save as `fix-migration-heads.sh`:
```bash
#!/bin/bash
source .venv/bin/activate

echo "🔍 Checking migration heads..."
heads=$(SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads 2>/dev/null | grep "(head)")
head_count=$(echo "$heads" | grep -c "(head)")

if [ "$head_count" -eq 1 ]; then
    echo "✅ Single head found - no action needed"
    exit 0
elif [ "$head_count" -eq 0 ]; then
    echo "❌ No migration heads found!"
    exit 1
else
    echo "⚠️  Multiple heads detected:"
    echo "$heads"

    # Extract revision IDs
    head1=$(echo "$heads" | sed -n '1p' | awk '{print $1}')
    head2=$(echo "$heads" | sed -n '2p' | awk '{print $1}')

    echo "Creating merge migration for: $head1 and $head2"

    # Create merge migration
    SERVER_NAME=localhost CACHE_TYPE=NullCache flask db merge $head1 $head2 -m "merge migration heads"

    echo "✅ Merge migration created"
    echo "Don't forget to commit: git add migrations/ && git commit -m 'Merge migration heads'"
fi
```

## 📊 Migration History Visualization

Check your migration tree:
```bash
# Show migration history
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db history

# Show current version
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db current
```

## 🎓 Best Practices

### 1. **Check Heads After Every Upstream Merge**
```bash
git merge upstream/main
./fix-migration-heads.sh  # Run immediately
```

### 2. **Keep Merge Migrations Descriptive**
```bash
# Good
flask db merge xxx yyy -m "merge upstream v1.3 migrations with custom user features"

# Bad
flask db merge xxx yyy -m "merge"
```

### 3. **Never Delete Migration Files**
- Even if they seem redundant
- Other deployments may depend on them
- Use merge migrations instead

### 4. **Test Migrations Locally**
```bash
# Always test upgrade after creating merge
flask db upgrade

# Test downgrade if needed
flask db downgrade -1
```

### 5. **Document Custom Migrations**
Keep a list of your custom migrations in `CUSTOM_MIGRATIONS.md`:
```markdown
## Our Custom Migrations
- `abc123def456` - Added user preferences table
- `789ghi012jkl` - Added custom analytics fields
```

## 🔧 Troubleshooting

### "Multiple head revisions are present"
**Solution**: Create merge migration (see Step 2 above)

### "Can't locate revision identified by 'xxx'"
**Cause**: Missing migration file
**Solution**:
- Check if migration exists in `migrations/versions/`
- Pull latest changes from your repo
- Never delete migration files

### "Target database is not up to date"
**Solution**:
```bash
flask db upgrade
```

### "Constraint already exists" after merge
**Cause**: Both migrations trying to create same constraint
**Solution**: Edit merge migration to remove duplicate operations

## 📚 Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Flask-Migrate Docs](https://flask-migrate.readthedocs.io/)
- Our test: `tests/test_migration_heads.py`

## 🎯 Quick Reference

```bash
# Check heads
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads

# Merge heads
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db merge <head1> <head2> -m "description"

# Upgrade database
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db upgrade

# View history
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db history

# Current version
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db current
```

Remember: **Always handle migration heads immediately after merging upstream!**
