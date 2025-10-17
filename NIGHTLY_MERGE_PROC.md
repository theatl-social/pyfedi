# Nightly Merge Procedure

## Purpose
This document outlines the standard procedure for merging upstream changes from the main PieFed repository into our fork.

## Prerequisites
- Ensure you have the upstream remote configured:
  ```bash
  git remote add upstream https://codeberg.org/rimu/pyfedi.git
  ```
- Virtual environment is set up with `uv venv`
- Dependencies installed with `uv pip install -r requirements.txt`

## Merge Procedure

### 1. Create New Feature Branch
```bash
# Create a new branch with today's date
git checkout -b feature/merge-upstream-$(date +%Y%m%d)
```

### 2. Check for Linting/Syntax Errors
```bash
# Activate virtual environment
source .venv/bin/activate

# Run ruff linter
ruff check . --config ruff.toml

# If errors are found, fix them:
# - Missing imports (especially werkzeug.security.generate_password_hash)
# - Indentation errors in CLI commands (must be inside register(app) function)
# - Undefined names
```

### 3. Commit Any Linting Fixes
```bash
# If you made linting fixes
git add -A
git commit -m "Fix linting errors - add missing imports and fix indentation"
```

### 4. Fetch Latest from Upstream
```bash
# Fetch the latest changes
git fetch upstream main --force

# Verify you have the latest
git log upstream/main --oneline -5
```

### 5. Merge Upstream Changes
```bash
# Perform the merge
git merge upstream/main

# If there are conflicts, resolve them carefully
# Pay special attention to:
# - app/cli.py (our test infrastructure additions)
# - config.py (environment variables)
# - Any API endpoints (maintain backwards compatibility)
```

### 6. Handle Merge Conflicts (if any)
If conflicts occur:
1. Open conflicted files in editor
2. Look for conflict markers: `<<<<<<<`, `=======`, `>>>>>>>`
3. Carefully merge changes, preserving:
   - Our test infrastructure code
   - Our custom CLI commands
   - Any local modifications
4. After resolving:
   ```bash
   git add <resolved-files>
   git commit
   ```

### 7. Verify Merge Success
```bash
# Check status
git status

# Run linting again
ruff check . --config ruff.toml

# Run critical tests
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py -v
```

### 8. Update Documentation
Update CLAUDE.md with merge information:
```markdown
### Merge History
- Successfully merged with upstream/main (commit <hash>) on <date>
- Branch: feature/merge-upstream-<date>
- Key additions from upstream:
  - [List major features/fixes]
```

### 9. Commit Documentation Updates
```bash
git add CLAUDE.md NIGHTLY_MERGE_PROC.md
git commit -m "Update documentation with merge notes - $(date +%Y%m%d)"
```

### 10. Update Version String (if applicable)
If there's a version string in the codebase, update it to include today's date:
```bash
# Find version strings
grep -r "VERSION.*2024\|VERSION.*2025" --include="*.py"

# Update as needed
git add <files-with-version>
git commit -m "Update version string to include $(date +%Y%m%d) date"
```

## Common Issues and Solutions

### Issue: CLI Commands Outside register() Function
**Symptom**: `F821 Undefined name 'app'` errors in app/cli.py

**Solution**: Ensure all `@app.cli.command()` decorators are properly indented inside the `register(app)` function

### Issue: Missing Imports
**Symptom**: `generate_password_hash` or other functions undefined

**Solution**: Add missing import at top of file:
```python
from werkzeug.security import generate_password_hash
```

### Issue: parse_communities Function Deleted
**Symptom**: Function accidentally removed during merge

**Solution**: Re-add the function after the `register(app)` function ends

## Post-Merge Checklist
- [ ] All linting errors fixed
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Version string updated (if applicable)
- [ ] Branch committed and clean

## Version History
- 2025-08-25: Initial merge procedure documented
- Last successful merge: 2025-08-25 (upstream/main commit aa2e9e85)
