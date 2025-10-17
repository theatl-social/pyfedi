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

### 2. Install Pre-commit Hooks (First Time Only)
```bash
# Activate virtual environment
source .venv/bin/activate

# Install pre-commit
pip install pre-commit

# Install git hooks
pre-commit install
```

Pre-commit hooks automatically check and fix:
- Python linting (ruff) with auto-fix
- Python formatting (ruff-format)
- Template linting (djlint) for HTML/Jinja2 files
- YAML/JSON validation
- Trailing whitespace and end-of-file issues
- Invalid `len()` usage in Jinja2 templates

### 3. Run Pre-commit on Current Branch
```bash
# Run all pre-commit hooks on all files
pre-commit run --all-files

# This will automatically fix many issues and report any that require manual intervention
# Common fixes applied automatically:
# - Trailing whitespace removal
# - End-of-file newlines
# - Code formatting

# If manual fixes are needed, make them and commit:
git add -A
git commit -m "Fix linting errors before merge"
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

# Run pre-commit hooks to verify everything passes
pre-commit run --all-files

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

### Issue: Pre-commit Hook Blocks Commit
**Symptom**: Pre-commit hooks fail and prevent git commit

**Solution**:
1. Review the error messages from pre-commit
2. Most issues are auto-fixed (trailing whitespace, formatting)
3. For issues requiring manual fix:
   - Ruff linting errors: Fix undefined variables, unused imports, etc.
   - djlint errors: Fix invalid Jinja2 syntax or `len()` usage
4. Run `pre-commit run --all-files` again to verify
5. If you need to skip hooks (NOT recommended): `git commit --no-verify`

### Issue: CLI Commands Outside register() Function
**Symptom**: `F821 Undefined name 'app'` errors in app/cli.py

**Solution**: Ensure all `@app.cli.command()` decorators are properly indented inside the `register(app)` function

### Issue: Missing Imports
**Symptom**: `generate_password_hash` or other functions undefined

**Solution**: Add missing import at top of file:
```python
from werkzeug.security import generate_password_hash
```

### Issue: Unused Variables in Migrations
**Symptom**: `F841 Local variable assigned but never used`

**Solution**: Prefix variable name with underscore: `_post_table` instead of `post_table`

### Issue: parse_communities Function Deleted
**Symptom**: Function accidentally removed during merge

**Solution**: Re-add the function after the `register(app)` function ends

## Post-Merge Checklist
- [ ] Pre-commit hooks installed (`pre-commit install`)
- [ ] Pre-commit checks passing (`pre-commit run --all-files`)
- [ ] All linting errors fixed (automatically by pre-commit)
- [ ] Templates pass djlint validation
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Version string updated (if applicable)
- [ ] Branch committed and clean

## Pre-commit Configuration

The repository includes a [.pre-commit-config.yaml](.pre-commit-config.yaml) file that defines:

1. **Python Quality**:
   - `ruff` - Fast Python linter with auto-fix
   - `ruff-format` - Code formatter

2. **Template Quality**:
   - `djlint` - Lints all HTML/Jinja2 templates using [.djlintrc](.djlintrc) config
   - Custom check for invalid `len()` usage in Jinja2

3. **General Checks**:
   - YAML/JSON validation
   - Merge conflict detection
   - Trailing whitespace removal (auto-fix)
   - End-of-file fixing (auto-fix)
   - Mixed line ending detection

All pre-commit hooks match the CI/CD pipeline configuration in [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml), ensuring local validation before push.

## Version History
- 2025-10-17: Added pre-commit hooks configuration and documentation
- 2025-08-25: Initial merge procedure documented
- Last successful merge: 2025-10-17 (upstream/main commit with pre-commit integration)
