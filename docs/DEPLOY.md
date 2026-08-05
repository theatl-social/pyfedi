# Deploying a release

Production runbook for the PeachPie fork. Registry is
`mikehdev/peachpie-compiled` on Docker Hub; the compose network is `pf_network`.

---

## 0. Before you start

Know which tag you are deploying and what it contains. Every build is pushed with
three tags pointing at the same image:

| tag | use |
|---|---|
| `v<version>` e.g. `v1.7.10-peachpie-20260805-hotfix2` | **deploy this** — version-pinned |
| `sha-<short>` e.g. `sha-3f9486e` | immutable, ties back to a `main` commit |
| `latest` | moving — do not pin production to it |

The image is **`linux/amd64` only**. On an arm64 machine (Apple Silicon) you must
pass `--platform linux/amd64` or the pull fails with
`no matching manifest for linux/arm64/v8`.

---

## 1. Preflight — always, before upgrading

Read-only. Reports anything that would block `flask db upgrade`.

```bash
docker run --rm \
  --network pf_network \
  --env-file ./.env.docker \
  --entrypoint /app/scripts/preflight.sh \
  mikehdev/peachpie-compiled:<tag>
```

Or against the running stack, which already has env and network attached:

```bash
docker compose exec web /app/scripts/preflight.sh
```

Two flags are not optional, and both fail in ways that point at the wrong thing:

- **`--entrypoint`** — the image sets `ENTRYPOINT ["./entrypoint.sh"]`, so a plain
  `docker run <image> <cmd>` silently ignores your command and starts gunicorn.
- **`--network pf_network`** — without it the container gets a fresh bridge
  network, cannot resolve the `db` host, and reports a connection error that
  reads like a database problem rather than a networking one.

| exit | meaning |
|---|---|
| `0` | safe to upgrade |
| `1` | blocked — the reason and remediation are printed |
| `2` | could not run the check (missing env, database unreachable) |

It checks alembic head alignment (the head in the image vs the revision recorded
in the database, and the migrations pending between them) and any data that would
block a pending migration.

**If it reports duplicates**, reconcile them before deploying. Do not delete rows
blindly — user rows own posts, comments and votes. Usually the oldest row is the
real account.

---

## 2. Capture rollback state

```bash
docker compose images                       # note the current image IDs
docker inspect --format '{{index .RepoDigests 0}}' \
  $(docker compose ps -q web)               # the digest you are rolling back to
```

Record the **current alembic revision** too — migrations are the part that does
not roll back cleanly:

```bash
docker compose exec web uv run --no-sync flask db current
```

---

## 3. Pull and deploy

```bash
docker pull mikehdev/peachpie-compiled:<tag>

# verify you got the bits CI built
docker image inspect mikehdev/peachpie-compiled:<tag> \
  --format '{{index .RepoDigests 0}}'
# compare against the digest in the build run's log

docker compose up -d
```

`entrypoint.sh` runs `flask db upgrade` as root on web startup, so migrations
apply automatically once the container starts. That is why preflight comes first.

---

## 4. Verify

```bash
docker compose ps                    # all services Up, none restarting
docker compose logs --tail=50 web
docker compose logs --tail=50 celery
```

**Watch celery specifically.** It is the service most likely to fail on a
release, and it crash-loops rather than exiting, so `docker compose ps` alone can
look healthy for a moment. A known signature:

```
error: failed to remove file `/app/.venv/.../_editable_impl_pyfedi.pth`:
Permission denied (os error 13)
pyfed-celery exited with code 2 (restarting)
```

That means an entrypoint lost `uv run --no-sync` — `/app/.venv` is root-owned and
the worker runs as `python`. See `entrypoint_celery.sh`.

Then confirm the app and the migration state:

```bash
curl -ILfSs http://localhost:8030/health | head -1
docker compose exec web uv run --no-sync flask db current   # should be the new head
```

---

## 5. Rollback

Application only (no migration applied, or the migration is
backward-compatible):

```bash
docker pull mikehdev/peachpie-compiled:<previous-tag>
# point compose at the previous tag, then:
docker compose up -d
```

**If a migration applied**, roll the schema back *first*, then the image —
otherwise the old code meets a newer schema:

```bash
docker compose exec web uv run --no-sync flask db downgrade <previous-revision>
```

Check the migration's `downgrade()` before relying on it. Merge migrations are
no-ops by design and cannot undo anything; data migrations may not be reversible
at all. When in doubt, restore from backup rather than downgrading.

---

## Release-specific notes

### v1.7.10-peachpie-20260805 and later

- **`20260805_local_user_uniq`** adds unique indexes on `lower(user_name)` and
  `lower(email)` for local users. The build takes an **exclusive write lock** on
  `user`. On a large instance, create the two indexes `CONCURRENTLY` by hand and
  stamp the revision instead — `CONCURRENTLY` cannot run inside Alembic's
  transaction. The migration refuses to run against duplicate data and lists
  every offender.
- **The private-registration IP allowlist now enforces.** It was previously inert
  (always returned `True`). If `PRIVATE_REGISTRATION_IPS` or
  `PRIVATE_REGISTRATION_ALLOWED_IPS` is set, it now applies — and it reads
  `request.remote_addr`, so your reverse proxy must set the forwarded headers
  correctly or you can lock yourself out of the admin API.
- **19 admin API endpoints are live again** at `/api/alpha/admin/*` after five
  months of 404s, still gated behind `PRIVATE_REGISTRATION_ENABLED`
  (default off).

---

## Building an image

Only from `main`, after CI is green:

```bash
gh workflow run docker-build-push.yml \
  -f branch=main \
  -f tag=v<version> \
  -f additional_tags=latest
```

Then take the digest from the run log (`pushing manifest for ...@sha256:...`) and
record it with the release.
