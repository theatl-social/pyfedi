# Handover: Celery worker stability

## Status

Implementation has not started. The approved design is committed as
`2e9870bc` on branch `20260805/celery-modern-settings`, in the isolated
worktree:

`/Users/michael/code/pyfedi/.worktrees/20260805-celery-modern-settings`

The branch is based on `cc270d0e`, the merged
`1.7.8-peachpie-20260805` release. The primary checkout at
`/Users/michael/code/pyfedi` is clean on `main` at the same revision.

## Production symptom

Federated Lemmy Like processing can return HTTP 200 from `/inbox`, then fail in
the Celery worker with:

```text
redis.exceptions.LockNotOwnedError: Cannot release a lock that's no longer owned
```

The observed path is:

```text
process_inbox_request -> process_upvote -> PostReply.vote
```

The failure is raised while leaving the outer Redis lock in
`PostReply.vote()`. The vote method commits work before the context exits, so
the log line alone does not establish whether a specific incoming vote was
persisted. Do not replay or retry federation activities manually.

## Confirmed root cause

Current outer vote locks use a ten-second TTL:

- `app/models.py`: `Post.vote()` uses `lock:post:{id}`, `timeout=10`.
- `app/models.py`: `PostReply.vote()` uses `lock:post_reply:{id}`, `timeout=10`.

The database work and nested locks can take longer than ten seconds. Redis then
expires the key; if another worker acquires it, `redis-py` correctly refuses the
first worker's later release with `LockNotOwnedError`.

This fork previously fixed the same failure in commit `2610bf33` by changing
both outer vote locks to 30 seconds. That commit is not an ancestor of the
current branch: the later upstream merge replaced the methods and restored the
ten-second values. A minimal restoration is therefore preferred over lock
auto-renewal or swallowing the ownership exception.

## Celery warning causes

- `app/__init__.py` calls `celery.conf.update(app.config)`, passing every Flask
  setting to Celery. That leaks application `S3_REGION` and `S3_BUCKET` into
  Celery as deprecated uppercase options.
- The explicit JSON serializer settings and routing map use deprecated uppercase
  Celery names in `app/__init__.py`.
- `celery_worker_docker.py` and `celery_worker.default.py` use deprecated
  `CELERYD_MAX_*` names.
- No `broker_connection_retry_on_startup` setting is present.
- `entrypoint_celery.sh` starts Celery as root; it does not use the `gosu python`
  transition that the web entrypoint uses.

## Approved implementation scope

1. Restore the 30-second TTL for the outer post and reply vote locks, retaining
   their current names and six-second acquisition timeout.
2. Replace the broad Flask-to-Celery configuration merge with explicit,
   lowercase Celery configuration only:
   `broker_url`, `result_backend`, `task_serializer`, `result_serializer`,
   `accept_content`, `task_routes`, `worker_max_tasks_per_child`,
   `worker_max_memory_per_child`, and `broker_connection_retry_on_startup=True`.
3. Preserve the Redis URLs, JSON-only security allowlist, queues/routing map,
   1,000-task worker recycling, 512,000-KB memory recycling, and retry behavior.
4. Launch the Celery worker with `exec gosu python ...`, preserving its existing
   Celery application, concurrency, and queue arguments.
5. Add focused regression tests for the modern Celery settings and the 30-second
   lock arguments on both vote methods.

The canonical approved specification is
`docs/superpowers/specs/2026-08-05-celery-worker-stability-design.md`.

## Explicit non-goals

- No lock auto-renewal, no non-expiring locks, and no suppression of
  `LockNotOwnedError`.
- No changes to vote counts, ActivityPub permissions, federation retries,
  `VOTE_QUOTA`, queues, task routing, or S3 application clients.
- No Compose-level user override.
- No production configuration changes, image build, deployment, restart, or
  manual activity replay without separate user authorization.

## Verification and delivery

- Create tests before implementation. Use a fake/mocked Redis client to assert
  both outer vote methods request `timeout=30`; do not sleep in tests.
- Assert Celery's effective configuration retains the required lowercase values
  and contains no legacy keys introduced by the application configuration.
- Run the focused new tests, relevant existing vote tests, Ruff, template lint,
  and Docker build validation.
- Commit only implementation/test files plus the already-committed design and
  this handoff. Open a PR from this branch; do not force-push.
- After CI and user approval, merge first. Building a new image and promoting it
  to the live host remain separate authorized actions.

## Useful evidence commands

```bash
git merge-base --is-ancestor 2610bf33 HEAD
git show 2610bf33 -- app/models.py
git blame -L 2556,2564 app/models.py
git blame -L 3125,3132 app/models.py
```
