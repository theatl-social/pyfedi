---
name: merge-upstream
description: Use when merging upstream PieFed changes into our fork, syncing with upstream, or upgrading to a new upstream version. Triggers on phrases like "merge upstream", "sync fork", "upgrade version", or "pull upstream changes".
---

# Merge Upstream

## Overview

Procedure for merging upstream PieFed (codeberg.org/rimu/pyfedi) changes into our PeachPie fork. Multi-step process with conflict resolution, migration head management, dependency sync, and verification.

## Prerequisites

Verify before starting:
```bash
git remote -v | grep upstream
# Should show: https://codeberg.org/rimu/pyfedi.git
# If missing: git remote add upstream https://codeberg.org/rimu/pyfedi.git
```

## Procedure

Use TodoWrite to create a checklist from these steps. Mark each complete as you go.

### 1. Create Feature Branch

```bash
git checkout main
git pull origin main
git checkout -b YYYYMMDD/merge-upstream-vXYZ
```

Use today's date in YYYYMMDD format and the target upstream version.

### 2. Run Ruff on Current Branch

```bash
uvx ruff check .
```

Note: `pre-commit run --all-files` may fail on Python 3.14 due to `pillow-avif-plugin` build issues. Use `uvx ruff check .` directly instead.

### 3. Fetch and Inspect Upstream

```bash
git fetch upstream main --force
git log upstream/main --oneline -10
git log HEAD..upstream/main --oneline
git log HEAD..upstream/main --oneline -- migrations/
```

Review what's coming in. Note any migrations, model changes, or new dependencies.

### 4. Merge Upstream

```bash
git merge upstream/main
```

If clean merge, skip to Step 6.

### 5. Resolve Conflicts

**Established pattern — process in this order:**

1. **Translations** — accept upstream for all `.po` files:
   ```bash
   for f in app/translations/*/LC_MESSAGES/messages.po; do
     git checkout --theirs "$f" && git add "$f"
   done
   ```

2. **requirements.txt** — delete it (we use `pyproject.toml`):
   ```bash
   git rm requirements.txt
   ```

3. **Non-critical Python/templates/static** — accept upstream for files where we have no custom code. This covers most files.

4. **Critical files** — take upstream then restore our customizations:
   - **app/models.py** — restore `privacy_url = db.Column(db.String(256))` after `tos_url`
   - **app/admin/forms.py** — restore `privacy_url` field
   - **app/admin/routes.py** — restore `privacy_url` in save and load blocks (next to `tos_url`)
   - **app/templates/base.html** — restore PeachPie footer branding
   - **pyfedi.py** — typically safe to take upstream
   - **entrypoint_celery.sh / entrypoint_async.sh** — ensure they use `uv run` prefix

### 6. Check Migration Heads

Cannot run `flask db heads` locally (needs Redis/Postgres). Use this Python script instead:

```python
python3 -c "
import os, re
versions_dir = 'migrations/versions'
revisions = {}
all_down = set()
for f in os.listdir(versions_dir):
    if not f.endswith('.py') or f == '__pycache__':
        continue
    content = open(os.path.join(versions_dir, f)).read()
    rev_match = re.search(r'^revision\s*=\s*[\"\'](.*?)[\"\']', content, re.M)
    down_match = re.search(r'^down_revision\s*=\s*(.*?)$', content, re.M)
    if rev_match and down_match:
        rev = rev_match.group(1)
        down_raw = down_match.group(1).strip()
        revisions[rev] = (down_raw, f)
        for d in re.findall(r'[\"\'](.*?)[\"\']', down_raw):
            all_down.add(d)
heads = [r for r in revisions if r not in all_down]
print(f'Heads: {len(heads)}')
for h in heads:
    print(f'  {h} <- {revisions[h][1]}')
"
```

If multiple heads, create a merge migration file manually:
```python
revision = 'merge_YYYYMMDD'
down_revision = ('<head1>', '<head2>')
def upgrade(): pass
def downgrade(): pass
```

### 7. Sync Dependencies

Diff upstream's `requirements.txt` against our `pyproject.toml` for new packages:
```bash
git show upstream/main:requirements.txt
```

Add any new dependencies to `pyproject.toml` and run `uv lock`.

### 8. Set Version

Update version in both places:
- `app/constants.py`: `VERSION = "X.Y.Z"`
- `pyproject.toml`: `version = "X.Y.Z"`

### 9. Verify Fork Customizations

Check all customizations survived the merge:
- `privacy_url` in models.py, admin/forms.py, admin/routes.py
- PeachPie footer in base.html (`grep theatl app/templates/base.html`)
- Private registration API (`ls app/api/admin/private_registration.py`)
- Entrypoints use `uv run` (`grep "uv run" entrypoint*.sh`)

### 10. Run Ruff and Tests

```bash
uvx ruff check .
SERVER_NAME=localhost uv run pytest tests/test_field_consistency_simple.py -v
```

Fix ruff errors with `uvx ruff check . --fix`. If tests fail due to missing module, add it to pyproject.toml.

### 11. Update CLAUDE.md Merge History

Update the `### Merge History` section with date, branch, commit hash, and key additions.

### 12. Commit, Push, PR, Merge, Build

```bash
git commit --no-verify -m "Merge upstream PieFed vX.Y.Z into PeachPie fork"
git push -u origin YYYYMMDD/merge-upstream-vXYZ
gh pr create --title "Merge upstream PieFed vX.Y.Z" ...
gh pr merge <number> --merge --delete-branch=false
gh workflow run docker-build-push.yml -f branch=main -f tag=vX.Y.Z -f additional_tags=latest
```

## Common Issues

| Problem | Solution |
|---------|----------|
| Multiple migration heads | Step 6 — create merge migration manually |
| `pre-commit` build failures | Use `uvx ruff check .` instead |
| Missing module in tests | New upstream dependency — add to pyproject.toml |
| `celery: not found` in Docker | Entrypoint missing `uv run` prefix |
| `content_type` before definition | Upstream bug — move extra_args inside loop |
| Duplicate function name | Upstream bug — rename the second one |
