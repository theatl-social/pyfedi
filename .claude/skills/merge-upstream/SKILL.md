---
name: merge-upstream
description: Use when merging upstream PieFed changes into our fork, syncing with upstream, or upgrading to a new upstream version. Triggers on phrases like "merge upstream", "sync fork", "upgrade version", or "pull upstream changes".
---

# Merge Upstream

## Overview

Procedure for merging upstream PieFed (codeberg.org/rimu/pyfedi) changes into our fork. This is a multi-step process with conflict resolution, migration head management, and verification.

## When to Use

- Syncing our fork with upstream PieFed
- Upgrading to a new upstream release
- Pulling in upstream bug fixes or features

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
git checkout -b YYYYMMDD/merge-upstream
```

Use today's date in YYYYMMDD format.

### 2. Run Pre-commit on Current Branch

Fix any existing lint issues BEFORE merging to keep merge diffs clean:

```bash
pre-commit run --all-files
```

If fixes are made:
```bash
git add -A
git commit -m "fix: Lint cleanup before upstream merge"
```

### 3. Fetch and Inspect Upstream

```bash
git fetch upstream main --force
git log upstream/main --oneline -10
git log HEAD..upstream/main --oneline
```

Review what's coming in. Note any migrations, model changes, or breaking changes.

### 4. Merge Upstream

```bash
git merge upstream/main
```

If clean merge, skip to Step 6.

### 5. Resolve Conflicts (if any)

Conflict resolution priorities — preserve OUR versions of:
- **app/cli.py** — our test infrastructure and custom CLI commands
- **config.py** — our environment variables and settings
- **API endpoints** — maintain backwards compatibility
- **Templates with our customizations** — check carefully

For each conflicted file:
1. Read the file and understand both sides
2. Resolve preserving our customizations while incorporating upstream changes
3. Stage resolved files: `git add <file>`

After all conflicts resolved:
```bash
git commit
```

### 6. Check Migration Heads

```bash
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads
```

If multiple heads are shown:
```bash
# Extract the two head revision IDs from the output
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db merge <head1> <head2> -m "merge migration heads after upstream merge"
git add migrations/versions/*.py
git commit -m "fix: Merge migration heads after upstream sync"
```

Verify single head:
```bash
SERVER_NAME=localhost CACHE_TYPE=NullCache flask db heads
```

### 7. Run Pre-commit After Merge

```bash
pre-commit run --all-files
```

Fix any issues introduced by the merge. Commit fixes separately:
```bash
git add -A
git commit -m "fix: Lint fixes after upstream merge"
```

### 8. Run Tests

```bash
SERVER_NAME=localhost uv run pytest tests/test_field_consistency_simple.py -v
```

If tests fail, investigate and fix. Do NOT proceed with failing tests.

### 9. Update CLAUDE.md Merge History

Update the `### Merge History` section in CLAUDE.md with:
- Merge date
- Branch name
- Upstream commit hash (from `git log upstream/main --oneline -1`)
- Key additions from upstream (summarize from the log in Step 3)

```bash
git add CLAUDE.md
git commit -m "docs: Update merge history for upstream sync YYYYMMDD"
```

### 10. Push and Create PR

```bash
git push -u origin YYYYMMDD/merge-upstream
```

Then create a PR against main with a summary of upstream changes included.

## Common Issues

| Problem | Solution |
|---------|----------|
| Multiple migration heads | Step 6 — create merge migration |
| Pre-commit blocks commit | Fix issues, run `pre-commit run --all-files` again |
| `app` undefined in cli.py | Ensure decorators are inside `register(app)` function |
| Missing imports after merge | Check ruff output, add missing imports |
| Function deleted during merge | Re-add from upstream or our branch as appropriate |
| Model column missing | Check if upstream added migration we need to include |

## Decision Flowchart

```
Merge clean? ──yes──> Check migration heads
     │
     no
     │
     v
Resolve conflicts (preserve our customizations)
     │
     v
Check migration heads
     │
Single head? ──yes──> Run pre-commit
     │
     no
     │
     v
Create merge migration ──> Run pre-commit
     │
     v
Tests pass? ──yes──> Update docs, push, PR
     │
     no
     │
     v
Investigate and fix (do NOT proceed with failures)
```
