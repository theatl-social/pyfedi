# Claude Code Iterative Development Workflow

## 🚨 IMMUTABILITY CONSTRAINTS

**These elements are IMMUTABLE and must NEVER be changed:**

### Database Schema
- ❌ **NO column renames** in existing tables
- ❌ **NO table renames** 
- ❌ **NO constraint changes** (unique, foreign keys, indexes)
- ❌ **NO data type changes**

### Public API Endpoints  
- ❌ **NO changes to URL paths**: `/api/alpha/site`, `/api/alpha/user/{id}`, etc.
- ❌ **NO changes to query parameters**: `?page=`, `?limit=`, `?sort=`, etc.
- ❌ **NO changes to request/response field names** in public APIs
- ❌ **NO changes to HTTP methods** (GET, POST, PUT, DELETE)

### ActivityPub Federation
- ❌ **NO changes to federation endpoints**: `/c/{name}`, `/u/{name}`, `/post/{id}`
- ❌ **NO changes to ActivityPub JSON-LD structure**

## 🔄 MANDATORY TEST-FIRST WORKFLOW

### Phase 1: Pre-Change Validation
```bash
# 1. Always activate virtual environment
source .venv/bin/activate

# 2. Run baseline tests to ensure current system works
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py -v

# 3. All tests must pass ✅ before proceeding
# 4. If any tests fail ❌ - fix existing issues first
```

### Phase 2: Iterative Changes
```bash
# 5. Make ONE minimal atomic change (single field, single function, etc.)

# 6. Run related tests immediately after each change
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py -v

# 7. Tests pass ✅ → Continue to next change
# 8. Tests fail ❌ → Revert change, fix, repeat
```

### Phase 3: Integration Validation
```bash
# 9. After each logical grouping, run broader tests
SERVER_NAME=localhost python -m pytest tests/test_allowlist_html.py -v

# 10. Manual verification of affected functionality
# 11. Commit only when everything passes
```

## 🧪 AVAILABLE TESTS

### Database Schema Immutability Tests
```bash
# Test critical model columns haven't changed
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py::test_user_model_columns_exist -v
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py::test_post_model_columns_exist -v
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py::test_community_model_columns_exist -v

# Test naming consistency (user_name vs username)
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py::test_user_name_field_consistency -v
```

### Content Processing Tests
```bash
# Test HTML sanitization and security
SERVER_NAME=localhost python -m pytest tests/test_allowlist_html.py -v

# Test Markdown processing
SERVER_NAME=localhost python -m pytest tests/test_markdown_to_html.py -v
```

## 📋 SAFE CHANGE ZONES

### ✅ Safe to Modify
- **Internal application logic** (business rules, validation)
- **Template rendering** (HTML generation)
- **Internal function names** and **private methods**
- **CSS classes** and **frontend styling**
- **Configuration options** (within reason)
- **New optional database columns** (with proper migrations)

### ❌ Forbidden Changes
- Any database schema modifications
- Any public API changes
- Any ActivityPub federation changes
- Any field name changes that break consistency

## 🔧 ENVIRONMENT SETUP

### Initial Setup
```bash
# Create virtual environment
uv venv

# Install dependencies
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Daily Usage
```bash
# Always start with this
source .venv/bin/activate
export SERVER_NAME=localhost

# Verify baseline before starting work
python -m pytest tests/test_field_consistency_simple.py -v
```

## 🚨 EMERGENCY PROCEDURES

### If Tests Fail After Changes
```bash
# 1. Stop immediately
# 2. Revert the last change
git checkout -- <modified_files>

# 3. Verify tests pass again
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py -v

# 4. Make smaller, more focused change
# 5. Test again before proceeding
```

### If Database Schema Issues Detected
```bash
# 1. DO NOT attempt to "fix" by changing model definitions
# 2. Report the issue immediately
# 3. The database schema is immutable - find alternative solutions
```

## 📝 FIELD NAME CONSISTENCY RULES

### Single Source of Truth
- **Models** (`app/models.py`) are the canonical field definitions
- **Always check model first** before referencing field names
- **Use grep to verify consistency** across all layers

### Before Changing Any Field Reference
```bash
# Check current usage patterns
grep -r "user_name" app/
grep -r "username" app/

# Verify against actual model
python -c "from app.models import User; print([col.name for col in User.__table__.columns])"
```

### Layers That Must Stay Consistent
- Models (`app/models.py`)
- Forms (`app/*/forms.py`)
- API schemas (`app/api/alpha/schema.py`)
- Views (`app/api/alpha/views.py`)
- Templates (`app/templates/`)

## 🎯 SUCCESS CRITERIA

Each change session should:
1. ✅ Start with all baseline tests passing
2. ✅ Make incremental, tested changes
3. ✅ End with all tests still passing
4. ✅ Preserve all immutable constraints
5. ✅ Maintain field name consistency across all layers

Remember: **Test first, change incrementally, validate continuously.**