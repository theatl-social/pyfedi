# Handover: follow-ups after the v1.7.10 release

Written 2026-08-06. Everything below is **optional** — none of it blocks the
release. `main` is at `bad8dbee`, CI green, and the deployable image is
`mikehdev/peachpie-compiled:v1.7.10-peachpie-20260805-hotfix2`
(digest `sha256:cfdad8473bbdf1307e7d48ee19bfc2bbadde1a61678b654c1851c40b8edc50a0`,
built from `main@3f9486eb`).

Read `docs/DEPLOY.md` before touching anything deployment-related, and
`.claude/skills/merge-upstream/SKILL.md` ("Merge hazards learned the hard way")
before any upstream merge.

---

## Task 1 — `compose.yaml` cannot build (confirmed defect)

**Status:** diagnosed, not fixed. Small and self-contained; good first task.

```
$ docker compose -f compose.yaml build web
failed to solve: target stage runtime could not be found
exit=1
```

`Dockerfile` defines exactly one stage (`FROM ... AS builder`, line 2) but
`compose.yaml` requests `target: runtime` at lines 61, 86 and 113 (web, celery,
async). `compose.dev.yaml` and `compose.test.yml` correctly use
`target: builder`.

Almost certainly a merge leftover: upstream moved to a multi-stage Dockerfile
while this fork deliberately kept its single-stage one (Debian slim + uv + gosu
— see CLAUDE.md), and `compose.yaml` picked up upstream's stage name.

**Why nobody noticed:** production does not use this file (its containers are
`pyfed-web`/`pyfed-celery`; `compose.yaml` names them
`piefed_app1`/`piefed_celery1`), and CI's Docker Build Validation builds the
Dockerfile directly rather than through compose. It only breaks
`docker compose up` from a fresh clone.

**Fix:** change `target: runtime` → `target: builder` in the three services.

**Do not** instead add a `runtime` stage to the Dockerfile without checking with
the repo owner — the single-stage shape is a deliberate fork divergence.

**Verify:**
```bash
docker compose -f compose.yaml build web && echo OK
grep -n "target:" compose*.yml compose*.yaml   # all should read builder
```
Consider adding a CI step that runs `docker compose -f compose.yaml config -q`
plus a build, since Docker Build Validation demonstrably does not cover this.

---

## Task 2 — `SP-###` entries for three security fixes

**Status:** fixes are shipped and have regression tests; only the
`SECURITY_PATCHES.md` bookkeeping is missing.

| fix | test |
|---|---|
| IP allowlist was inert (read a `settings` row nothing ever wrote, so `is_ip_whitelisted()` always returned `True`) | `tests/security/test_admin_ip_allowlist.py` |
| `X-Forwarded-For` leftmost entry trusted, making the allowlist forgeable | same file |
| `check_rate_limit()` failed open on any Redis exception; its `flask.g` fallback was per-request and therefore inert | `tests/test_celery_settings.py` covers config; behaviour verified manually |

**Next free number is SP-025.** Check before assigning:
```bash
grep -n "^### SP-0" SECURITY_PATCHES.md | sort -t- -k2 -n | tail -3
```
`SECURITY_PATCHES.md` is **not in numeric order** — SP-024 (remember-me cookie)
sits below SP-023 in the file. An earlier attempt in this cycle assigned SP-024
twice because of exactly that. Grep for the number, do not eyeball the file.

Lower value than a typical SP entry: all three live in `app/api/admin/*`, which
is fork-only code upstream never touches, so there is no merge-conflict risk for
the entries to protect against. Worth doing for completeness, not urgency.

---

## Task 3 — optional `get_ip_address()` hardening (needs a decision first)

**Status:** deliberately not done. Documented as an accepted risk in
`docs/TRUSTED_CLIENT_IP.md` — read that file before touching this.

`app/__init__.py:45` and `app/utils.py:2138` read the **leftmost**
`X-Forwarded-For` entry, which is client-supplied. They feed the Flask-Limiter
key function (13 rate-limited endpoints), IP bans, country blocking, and the IP
recorded on users and posts.

This is currently safe **only** because `CF-Connecting-IP` is checked first and
the repo owner confirmed the origin is reachable only through Cloudflare. That is
a property of the network, not the code, and nothing tests it.

The hardening is one line — replace the raw-header fallback with
`request.remote_addr` — and is a **no-op** in the current topology.

**Do not apply it without confirming the proxy hop count with the repo owner.**
`ProxyFix` is configured `x_for=1` (trust exactly one hop). If the real hop count
between Cloudflare and the app differs, `remote_addr` resolves to the wrong entry
— and because it is the rate-limiter key, every user collapses into a single
shared bucket. That is an outage, not a vulnerability, and it is the more likely
way to cause harm here.

---

## Task 4 — worktree cleanup (housekeeping)

Four worktrees remain on disk; all their branches are merged.

```bash
git worktree list
git worktree remove <path>       # per worktree
git worktree prune
```
Confirm merged first: `git branch --merged main`.

---

## Task 5 — `app.db` still occasionally shows modified (minor)

**Status:** mostly fixed, one intermittent path remains.

`app.db` is a **git-tracked SQLite file** at the repo root. `Config` falls back to
`sqlite:///<repo>/app.db` whenever `DATABASE_URL` is unset or empty, so any test
calling a bare `create_app()` writes to it. Two such tests were fixed this cycle
(`test_private_registration_simple.py`, `test_private_registration_activitypub.py`
— both set `os.environ["DATABASE_URL"]` inside `setUp()`, which is too late
because `Config` attributes are evaluated at *import* time). It previously grew
12KB → 1.5MB per suite run; that no longer happens.

What remains is intermittent and harmless: after some full-suite runs
`git status --short app.db` shows the file modified, with **no size change**
(12288 bytes before and after), and other runs leave it clean. Consistent with
something opening a read-write connection and SQLite rewriting the header, rather
than any actual data being written.

Diagnostic that found the earlier offenders — it makes the writer fail loudly
instead of silently succeeding:
```bash
git checkout -- app.db
chmod 444 app.db
DATABASE_URL= SERVER_NAME=localhost SECRET_KEY=test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxx \
  CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// uv run pytest tests/ -q 2>&1 | grep "^FAILED\|^ERROR"
chmod 644 app.db && git checkout -- app.db
```
Note this did **not** reproduce on the last attempt — nothing failed under
`chmod 444`, which is why the remaining path is suspected to be a read-write
*open* rather than a write.

The durable fix is to stop `Config` silently falling back to a tracked file — for
example, require an explicit `DATABASE_URL` in test contexts, or move the default
to a temp path. Both are broader than this handover; confirm with the repo owner
first, since the fallback may be load-bearing for someone's local workflow.

If you just need a clean tree: `git checkout -- app.db`.

---

## Not tasks — known and accepted

Do **not** "fix" these; each was investigated and consciously left.

| item | why |
|---|---|
| `test_connection_pool_thread_safety.py::test_forked_workers_with_engine_recreation_safe` fails locally | macOS-only. `multiprocessing` uses `spawn` on macOS and `fork` on Linux, so the test's local function cannot pickle. Passes in CI. The repo owner explicitly scoped it out. |
| 3 skipped API tests (`test_api_instance_blocks`, `test_api_post_bookmarks`, `test_api_post_subscriptions`) | `communities_banned_from_all_users()` / `moderating_communities_ids_all_users()` use PostgreSQL `ARRAY_AGG` with no SQLite equivalent. Skips name the reason. |
| admin limiter's per-worker fallback is imprecise | When Redis is down the effective limit is workers x configured. A real bound, deliberately chosen over failing open. Redis remains the accurate shared store. |
| `User.user_name`/`email` TOCTOU | **Fixed** — `20260805_local_user_uniq` ships in this release. |
| Dockerfile labels say `authors="rimu"`, `source=codeberg.org/rimu/pyfedi` | Inherited from upstream. Cosmetic; only affects `docker inspect` provenance. |

---

## Traps that will cost you an hour

- **`app.db` is a git-tracked SQLite file at the repo root.** Any test calling a
  bare `create_app()` with an empty `DATABASE_URL` writes to it (it grew 12KB →
  1.5MB in one suite run). `Config` attributes are evaluated at *import* time, so
  setting `os.environ["DATABASE_URL"]` inside `setUp()` is too late. Always pass
  an explicit config with `SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"`. Check
  `git status --short app.db` before committing.
- **Never add files to the `-not -name` exclusion list in
  `.github/workflows/ci-cd.yml`.** That list quarantined ~40 tests — including
  the SQL-injection and private-registration security suites — which is how an
  entire admin API stayed unrouted in production for five months. It may contain
  only files the workflow runs in a separate step.
- **`tests/conftest.py` has a SQLite compatibility shim.** Read its module
  docstring before changing fixtures. `db.create_all()` does not complete on
  SQLite without it, and `sqlalchemy_searchable` attaches PostgreSQL DDL hooks at
  *both* the metadata and per-table level — clearing only the metadata level
  leaves teardown broken.
- **Import order:** `config` imports `app.constants` and `app/__init__` imports
  `config`. Importing `config` before `app` raises
  `ImportError: cannot import name 'Config' from partially initialized module`.
- **`uv run` after a privilege drop needs `--no-sync`.** `/app/.venv` is
  root-owned; without it the process dies with `Permission denied (os error 13)`.
  This crash-looped the celery worker in production. Guarded by
  `tests/test_celery_settings.py`.

---

## Baseline to verify against

```bash
DATABASE_URL= SERVER_NAME=localhost SECRET_KEY=test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxx \
  CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// uv run pytest tests/ -q
# expected: 1 failed, 891 passed, 95 skipped   (verified on main@bad8dbee)
# the 1 failure is the macOS-only PicklingError above

uvx ruff check .                      # All checks passed
uv run djlint app/templates --lint    # 296 files, 0 errors
git status --short app.db             # usually empty -- see Task 5 if not
```

Migration chain: 288 revisions, single head `20260805_local_user_uniq`, 1 root,
no dangling `down_revision` targets, all reachable.

---

## What shipped in this cycle, for context

PRs #81–#85, all merged with full CI green.

- **#81** celery worker stability — restored the 30s vote-lock TTL (an upstream
  merge had reset it to 10s, causing `LockNotOwnedError` on federated votes),
  modern lowercase Celery config, gosu privilege drop.
- **#82** upstream v1.7.10 merge. Removed upstream's "anoobis" proof-of-work gate
  entirely (its PoW result was discarded and the cookie set unconditionally —
  `curl -b anoobis=x` bypassed it). Found and fixed a **five-month production
  outage**: the v1.6.9 merge (`4c611576`) both dropped the imports that register
  the private-registration admin API *and* collapsed its blueprint `url_prefix`,
  leaving 19 endpoints 404ing. Un-quarantined ~40 CI-excluded tests, which
  exposed five more real bugs.
- **#83** hotfix — the gosu change crash-looped celery until `uv run --no-sync`
  was added.
- **#84** `scripts/preflight.sh`.
- **#85** deploy runbook, trusted-client-IP note, merge hazards in the skill.

Test suite went from 17 failed / 496 passed / 27 errors to 1 failed / 890 passed
/ 0 errors.
