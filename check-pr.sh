#!/bin/bash
# PR Pre-Check Script
# Run this before creating any Pull Request

set -e  # Exit on any error

echo "🔍 Running PR Pre-Checks..."
echo "================================"

# Activate virtual environment
source .venv/bin/activate

# 1. Python linting
echo ""
echo "1️⃣  Checking Python code with ruff..."
if ruff check .; then
    echo "   ✅ Python linting passed"
else
    echo "   ❌ Python linting failed - run: ruff check . --fix"
    exit 1
fi

# 2. Template linting
echo ""
echo "2️⃣  Checking template formatting with djlint..."
if djlint app/templates --check > /dev/null 2>&1; then
    echo "   ✅ Template formatting passed"
else
    echo "   ❌ Template formatting needed - run: djlint app/templates --reformat --indent 4"
    exit 1
fi

# 3. Template validation
echo ""
echo "3️⃣  Validating template syntax..."
if grep -r "len(" app/templates/ | grep -v "length" > /dev/null 2>&1; then
    echo "   ❌ Found len() usage in templates - use |length filter instead"
    echo "   Files with issues:"
    grep -r "len(" app/templates/ | grep -v "length"
    exit 1
else
    echo "   ✅ Template syntax validation passed"
fi

# 4. Migration heads
echo ""
echo "4️⃣  Checking database migration heads..."
heads=$(SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads 2>/dev/null | grep "(head)" | wc -l)
if [ "$heads" -gt 1 ]; then
    echo "   ❌ Multiple migration heads detected!"
    echo "   Run: ./fix-migration-heads.sh"
    SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads
    exit 1
elif [ "$heads" -eq 0 ]; then
    echo "   ⚠️  No migration heads found (might be normal for fresh setup)"
else
    echo "   ✅ Single migration head found"
fi

# 5. Field consistency tests
echo ""
echo "5️⃣  Running field consistency tests..."
if SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_field_consistency_simple.py -v > /dev/null 2>&1; then
    echo "   ✅ Field consistency tests passed"
else
    echo "   ❌ Field consistency tests failed"
    echo "   Run: SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_field_consistency_simple.py -v"
    exit 1
fi

# 6. Migration tests
echo ""
echo "6️⃣  Running migration tests..."
if SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_migration_heads.py -v > /dev/null 2>&1; then
    echo "   ✅ Migration tests passed"
else
    echo "   ❌ Migration tests failed"
    echo "   Run: SERVER_NAME=localhost CACHE_TYPE=NullCache python -m pytest tests/test_migration_heads.py -v"
    exit 1
fi

# 7. API Blueprint check (if script exists)
echo ""
echo "7️⃣  Checking API blueprint registration..."
if [ -f "check_api_blueprints.py" ]; then
    if SERVER_NAME=localhost python check_api_blueprints.py > /dev/null 2>&1; then
        echo "   ✅ API blueprints properly registered"
    else
        echo "   ⚠️  API blueprint check had warnings (non-critical)"
    fi
else
    echo "   ⏭️  Skipping (check_api_blueprints.py not found)"
fi

echo ""
echo "================================"
echo "✅ All pre-checks passed! Ready to create PR."
echo ""
echo "Next steps:"
echo "1. git add <files>"
echo "2. git commit -m 'your message'"
echo "3. git push origin <branch>"
echo "4. Create PR on GitHub"
