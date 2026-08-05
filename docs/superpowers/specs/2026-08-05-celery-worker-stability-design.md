# Celery worker stability design

## Goal

Remove the Celery 6 configuration deprecation warnings and root-worker warning,
and restore reliable federated post and reply voting after an upstream merge
reverted this fork's Redis vote-lock timeout fix.

## Scope

### Vote locks

- Set the outer `Post.vote()` and `PostReply.vote()` Redis locks to a 30-second
  lifetime while preserving their current lock names and six-second acquisition
  timeout.
- Do not catch or suppress `LockNotOwnedError`, add auto-renewal, alter vote
  accounting, or change ActivityPub retry behavior. A failed release indicates a
  real loss of exclusive ownership; the corrective action is to prevent normal
  vote transactions from expiring at the known-too-short ten-second boundary.
- Cover both vote methods with regression tests that assert their Redis locks
  are requested with the 30-second lifetime.

## Celery configuration

- Stop passing the complete Flask configuration dictionary to Celery. The broad
  merge leaks unrelated uppercase application settings such as `S3_REGION` and
  `S3_BUCKET` into Celery, where they are interpreted as deprecated Celery
  options.
- Configure only the required Celery options using supported lowercase names:
  `broker_url`, `result_backend`, `task_serializer`, `result_serializer`,
  `accept_content`, `task_routes`, `worker_max_tasks_per_child`,
  `worker_max_memory_per_child`, and `broker_connection_retry_on_startup`.
- Preserve the existing Redis broker/result URLs, JSON-only serializer
  allowlist, three queues (`celery`, `background`, `send`), routing map, worker
  recycling limits (1,000 tasks and 512,000 KB), and startup retry behavior.
- Keep application S3 settings as Flask configuration only; this change does
  not alter application S3 clients or Celery's unused S3 result backend.

## Worker privilege drop

- Change only the Celery entrypoint to execute the worker with the existing
  `python` account through `gosu`, matching the web entrypoint.
- Retain the same Celery application, concurrency, and queue arguments.
- Do not set a Compose-level `user`, because the image entrypoint remains
  responsible for its own process privilege transition.

## Verification

- Add focused tests for the modern Celery settings and both vote-lock timeout
  call sites.
- Run those tests plus the existing vote/profile tests, Ruff, template lint,
  and a Docker build.
- Open a PR after verification. Building or deploying a new image, changing
  runtime configuration, and restarting production services require separate
  authorization.
