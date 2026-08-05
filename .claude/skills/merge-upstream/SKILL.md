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
   - **app/community/routes.py** — if upstream adds `from app.api.alpha.views import cached_modlist_for_community, cached_modlist_for_user`, this creates a circular import. Our fork owns these functions in `app/shared/community.py`. Fix:
     - In `app/community/routes.py`: change import to `from app.shared.community import cached_modlist_for_community, cached_modlist_for_user` (at the function-body level, not module level, to be safe)
     - In `app/api/alpha/views.py`: if upstream re-adds the function definitions, replace them with a re-export: `from app.shared.community import cached_modlist_for_community, cached_modlist_for_user  # noqa: E402, F401`
     - Tests in `tests/test_ci_fixes.py` enforce this architecture (they check that `views.py` imports from `shared.community`, and that `community/routes.py` does NOT import from `views.py`). If CI fails on these tests after merge, this is the fix.

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
- `privacy_url` in models.py (Site model, after `tos_url`), admin/forms.py, admin/routes.py
- PeachPie footer in base.html (`grep theatl app/templates/base.html`)
- Private registration API — **verify the routes are registered, not that the file exists**:
  ```bash
  SERVER_NAME=localhost uv run pytest tests/test_admin_api_routes_registered.py -v
  ```
  This checklist used to say `ls app/api/admin/private_registration.py`. That check
  passed continuously from 2026-03-06 to 2026-08-05 while the entire admin API was
  **unrouted and 404ing in production**: the v1.6.9 merge (`4c611576`) dropped the two
  `from app.api.admin import ...` lines at the end of `app/api/alpha/__init__.py`, and
  Flask only registers a route when its decorator actually executes. The file existed
  the whole time. Check behaviour, not artifacts.
- Entrypoints use `uv run` (`grep "uv run" entrypoint*.sh`), and every invocation
  that follows a privilege drop keeps `--no-sync`:
  ```bash
  grep -n "gosu python" entrypoint*.sh   # each must also carry --no-sync
  ```
  `/app/.venv` is built by `RUN uv sync` with no `USER` in the Dockerfile, so it is
  root-owned. Without `--no-sync`, `uv run` re-syncs the editable install at startup
  and the unprivileged user cannot delete the root-owned `.pth` — the worker
  crash-loops with `Permission denied (os error 13)`. `entrypoint.sh` masks this
  because its root-side `flask db upgrade` syncs first, so it is only *incidentally*
  safe. Guarded by `tests/test_celery_settings.py`.
- **Route surface is unchanged** (see "Merge hazards" below):
  ```bash
  SERVER_NAME=localhost uv run python -c "
  from app import create_app; from config import Config
  class C(Config): TESTING=True; CACHE_TYPE='NullCache'
  app=create_app(C); print(len(list(app.url_map.iter_rules())), 'routes')"
  ```
  Compare against the pre-merge count. A drop means routes were lost; a *silent
  relocation* will not change the count at all, which is why the route tests above
  assert exact paths.
- **Security patches still apply (CRITICAL):**
  ```bash
  SERVER_NAME=localhost uv run pytest tests/security/ -v
  ```
  See `SECURITY_PATCHES.md`. Each `SP-###` patch has a regression test. If any of these fail, an upstream change has reverted a security patch — re-apply the patch and resolve the conflict in our favor before continuing. **Do not proceed with the merge until `tests/security/` is green.**

### 10. Run Ruff and Tests

```bash
uvx ruff check .
SERVER_NAME=localhost uv run pytest tests/test_field_consistency_simple.py -v
SERVER_NAME=localhost uv run pytest tests/security/ -v
SERVER_NAME=localhost uv run pytest tests/test_ci_fixes.py -v
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

## Merge hazards learned the hard way

These are the failure modes that have actually bitten this fork. All of them
auto-merge cleanly and pass lint — none announce themselves.

### Shared blueprint names silently relocate routes

The fork and upstream can both declare an object with the same name in the same
file. Conflict resolution keeps one line, and everything mounted on it moves.

Concretely: this fork had
`ApiBlueprint("Admin", url_prefix="/api/alpha/admin")`. Upstream v1.6.9 added its
*own* `ApiBlueprint("Admin", url_prefix="/api/alpha")`, spelling `/admin/...` in
its route decorators instead. The merge kept upstream's line, and because the
fork's decorators are bare (`"/private_register"`, relying on the prefix to supply
`/admin`), all 19 endpoints moved to `/api/alpha/private_register` — including
`PUT`/`DELETE /api/alpha/user/<id>`, landing secret-gated admin routes in the
frozen public namespace.

**Check:** after merging, diff the blueprint declarations in
`app/api/alpha/__init__.py` against the pre-merge version. Fork-owned blueprints
should have fork-specific names (`private_admin_bp`, `"PrivateAdmin"`) precisely
so upstream cannot collide with them.

### Load-bearing imports look like dead code

A Flask route exists only when its `@route` decorator *executes*, which requires
the module to be imported. `app/api/admin/routes.py` is imported by exactly one
line at the bottom of `app/api/alpha/__init__.py` and nothing else. It reads like
an unused import — ruff does not flag it (`F401` is ignored) and removing it
breaks nothing at import time.

That line was dropped in the v1.6.9 merge and the entire admin API 404'd in
production for **five months and six upstream merges**.

**Check:** `tests/test_admin_api_routes_registered.py` asserts the live `url_map`.
Any similar "import for side effect" needs the same treatment — assert the
*effect*, not the import.

### Verify behaviour, never artifacts

Every safeguard that failed here was checking a proxy for the thing it cared
about:

| check | why it passed while broken |
|---|---|
| `ls app/api/admin/private_registration.py` | the file existed the whole time |
| `-not -name` exclusions in `ci-cd.yml` | ~40 tests never ran, including the security suites |
| `except Exception: pytest.skip(...)` in a fixture | reported "skipped", not "failed" |

**Never add a file to the `-not -name` exclusion list in `.github/workflows/ci-cd.yml`
to make CI green.** That list may only contain files the workflow runs in a
separate step. Fix the test, or mark it `skipif` with a stated reason so the skip
is visible in the run output.

### Regressions that recur every merge

Some fork changes sit exactly where upstream keeps editing, and have regressed
repeatedly. Each now has a guard test — run them all after every merge:

| what | guard |
|---|---|
| `Post.generate_ap_id` federation-safe form (regressed 3x) | `tests/test_post_slug.py` |
| `cached_modlist_*` circular-import architecture | `tests/test_ci_fixes.py` |
| vote lock TTLs (upstream reset 30s -> 10s) | `tests/test_vote_lock_timeout.py` |
| Celery settings + entrypoint privilege drop | `tests/test_celery_settings.py` |
| admin API routing | `tests/test_admin_api_routes_registered.py` |
| anoobis stays removed | `tests/test_anoobis_removed.py` |

### Upstream code is not automatically correct

Fix upstream bugs found while merging rather than importing them, and record it
in the merge commit. Examples from v1.7.10 alone: `os.environ.get("")` (an empty
env key, so two config values could never be set), and a `raise` immediately
before `abort(403)` that made the abort dead code and turned a rejection into a
500 leaking `SERVER_NAME`.

## Common Issues

| Problem | Solution |
|---------|----------|
| Multiple migration heads | Step 6 — create merge migration manually |
| `pre-commit` build failures | Use `uvx ruff check .` instead |
| Missing module in tests | New upstream dependency — add to pyproject.toml |
| `celery: not found` in Docker | Entrypoint missing `uv run` prefix |
| `content_type` before definition | Upstream bug — move extra_args inside loop |
| Duplicate function name | Upstream bug — rename the second one |
| `ImportError: cannot import name 'cached_modlist_for_community'` (circular import) | See Step 5 item 4 — fix `community/routes.py` and `views.py` imports to use `app.shared.community` |
| `test_ci_fixes.py` failures about `cached_modlist` | Same fix — our fork's architecture requires these functions in `shared/community.py` |
