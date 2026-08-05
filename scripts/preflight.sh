#!/usr/bin/env bash
#
# Pre-deploy safety check. Read-only: it inspects the database and changes
# nothing.
#
# Reports, and exits non-zero on anything that would block `flask db upgrade`:
#   * alembic head alignment -- the head in this image vs the revision actually
#     recorded in the target database, plus the migrations pending between them
#   * duplicate local usernames/emails, which block 20260805_local_user_uniq
#
# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
#
# The image sets ENTRYPOINT ["./entrypoint.sh"], so it must be overridden --
# otherwise the container just starts gunicorn and ignores the command:
#
#   docker run --rm \
#     --network pf_network \
#     --env-file ./.env.docker \
#     --entrypoint /app/scripts/preflight.sh \
#     mikehdev/peachpie-compiled:<tag>
#
# `--network pf_network` matters: without it the container gets a fresh bridge
# network and cannot resolve the `db` host, so it fails with a connection error
# that looks like a database problem rather than a networking one. The name is
# pinned in compose.yaml (`name: pf_network`), so it is not project-prefixed.
#
# Against a running stack you can equivalently use the existing service, which
# already has the env and network attached:
#
#   docker compose exec web /app/scripts/preflight.sh
#
# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
#   0  safe to run `flask db upgrade`
#   1  blocked -- see the reported reason
#   2  could not run the check (missing config, database unreachable)
#
# Deliberately NOT wired into the container entrypoints. As a startup gate this
# would refuse to boot a brand-new install (no alembic_version row yet is the
# normal state for one) and would turn "one migration cannot apply" into a full
# outage. The hard guarantee lives in the migration itself, which refuses to run
# against violating data and lists every duplicate.

set -uo pipefail

cd /app || {
    echo "preflight: /app not found -- is this running inside the image?" >&2
    exit 2
}

export FLASK_APP=pyfedi.py

if [ -z "${DATABASE_URL:-}" ]; then
    echo "preflight: DATABASE_URL is not set." >&2
    echo "  Pass the app's environment, e.g. --env-file ./.env.docker" >&2
    exit 2
fi

# Show which database is being inspected, with any password redacted, so the
# output is unambiguous when several environments are in play.
printf 'preflight: target %s\n\n' \
    "$(printf '%s' "$DATABASE_URL" | sed -E 's#(://[^:/@]+):[^@]*@#\1:***@#')"

# --no-sync: /app/.venv is root-owned (built by `RUN uv sync` with no USER in
# the Dockerfile). Without it, `uv run` tries to rewrite the editable install
# and fails as an unprivileged user -- the bug that crash-looped the celery
# worker. The image is built with `uv sync --frozen`, so nothing needs syncing.
uv run --no-sync flask preflight
status=$?

echo
if [ "$status" -eq 0 ]; then
    echo "preflight: OK -- safe to deploy and run \`flask db upgrade\`."
else
    echo "preflight: BLOCKED (exit $status) -- resolve the above before deploying."
fi
exit "$status"
