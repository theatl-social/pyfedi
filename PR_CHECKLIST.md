# Pull Request Pre-Check Checklist

This checklist MUST be completed before creating any Pull Request to ensure CI/CD passes.

## 🔍 Pre-PR Checklist

### 1. Python Code Quality
```bash
# Run ruff linting
source .venv/bin/activate
ruff check .

# Fix auto-fixable issues
ruff check . --fix
```

### 2. Template Linting
```bash
# Check all templates with djlint
source .venv/bin/activate
djlint app/templates --check

# Auto-format templates if needed
djlint app/templates --reformat --indent 4
```

### 3. Template Validation
```bash
# Check for invalid len() usage (should use |length filter)
grep -r "len(" app/templates/ | grep -v "length"

# If found, replace len(variable) with variable|length
```

### 4. Database Migration Checks ⚠️ CRITICAL
```bash
# Check for multiple migration heads
source .venv/bin/activate
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads

# If multiple heads exist, merge them (see MIGRATION_MANAGEMENT.md)
```

### 5. Core Test Suite
```bash
# Run field consistency tests (immutability checks)
SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_field_consistency_simple.py -v

# Run migration head tests
SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_migration_heads.py -v
```

### 6. API Blueprint Registration
```bash
# Verify all API blueprints are registered
SERVER_NAME=localhost python check_api_blueprints.py
```

## 🚀 Quick All-in-One Check Script
```bash
#!/bin/bash
echo "🔍 Running PR Pre-Checks..."

# Activate virtual environment
source .venv/bin/activate

# 1. Python linting
echo "1️⃣ Checking Python code..."
ruff check . || { echo "❌ Python linting failed"; exit 1; }

# 2. Template linting
echo "2️⃣ Checking templates..."
djlint app/templates --check || { echo "❌ Template formatting needed"; exit 1; }

# 3. Template validation
echo "3️⃣ Validating template syntax..."
if grep -r "len(" app/templates/ | grep -v "length"; then
    echo "❌ Found len() usage in templates - use |length filter instead"
    exit 1
fi

# 4. Migration heads
echo "4️⃣ Checking migration heads..."
heads=$(SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads 2>/dev/null | grep "(head)" | wc -l)
if [ "$heads" -gt 1 ]; then
    echo "❌ Multiple migration heads detected - run merge migration"
    exit 1
fi

# 5. Tests
echo "5️⃣ Running tests..."
SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_field_consistency_simple.py -v || { echo "❌ Field consistency tests failed"; exit 1; }
SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_migration_heads.py -v || { echo "❌ Migration tests failed"; exit 1; }

echo "✅ All pre-checks passed! Ready to create PR."
```

## 📝 Common Issues & Solutions

### Multiple Migration Heads
- **Cause**: Occurs when merging upstream changes that contain new migrations
- **Solution**: See `MIGRATION_MANAGEMENT.md`

### Template Formatting
- **Cause**: Templates not following djlint standards
- **Solution**: `djlint app/templates --reformat --indent 4`

### len() in Templates
- **Cause**: Using Python's len() instead of Jinja2's |length filter
- **Solution**: Replace `{% if len(items) > 0 %}` with `{% if items|length > 0 %}`

### Field Consistency Failures
- **Cause**: Database schema changes that violate immutability constraints
- **Solution**: Never rename columns, tables, or change constraints in existing tables

## 🎯 CI/CD Pipeline Overview

Our GitHub Actions workflow checks:
1. **Lint with ruff** - Python code quality
2. **Lint templates with djlint** - Template formatting
3. **Validate templates** - No invalid syntax (len() usage)
4. **Test migrations** - Single head, linear history
5. **Field consistency** - Database schema immutability

## 💡 Pro Tips

1. **Always run checks locally first** - Don't rely on CI/CD to catch issues
2. **Commit linting fixes separately** - Makes PR history cleaner
3. **Handle migrations immediately after merging upstream** - Don't let them pile up
4. **Use the all-in-one script** - Save it as `check-pr.sh` for quick validation

## 🔧 Setup Check Script

Save this as `check-pr.sh` in your project root:

```bash
chmod +x check-pr.sh
./check-pr.sh
```

This ensures all checks pass before pushing to GitHub!