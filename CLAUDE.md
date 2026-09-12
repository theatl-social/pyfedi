# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PieFed is a federated discussion and link aggregation platform (Reddit/Lemmy/Mbin alternative) written in Python with Flask. It implements ActivityPub federation for interoperability with the fediverse.

## Critical Development Commands

### Virtual Environment Setup (using uv)
```bash
# Install all dependencies (creates .venv automatically)
uv sync

# Or with dev dependencies
uv sync --dev
```

### Running Tests
```bash
# Run database schema immutability tests
SERVER_NAME=localhost uv run pytest tests/test_field_consistency_simple.py -v

# Run specific test
SERVER_NAME=localhost uv run pytest tests/test_field_consistency_simple.py::test_user_model_columns_exist -v

# Run all tests in a file
SERVER_NAME=localhost uv run pytest tests/test_allowlist_html.py -v

# Run production mirror tests (Docker environment)
./scripts/run-production-mirror-tests.sh
```

### Development Server
```bash
# Set environment variables (copy env.sample to .env first)
export SERVER_NAME=localhost
export DATABASE_URL=postgresql://pyfedi:pyfedi@localhost/pyfedi

# Run Flask development server
uv run flask run

# Run Celery worker (in separate terminal)
uv run celery -A celery_worker.celery worker --loglevel=info
```

### Database Management
```bash
# Initialize database
uv run flask init-db

# Create migration
uv run flask db migrate -m "description"

# Apply migrations
uv run flask db upgrade

# Downgrade migration
uv run flask db downgrade
```

### Adding Dependencies

```bash
# Add a new dependency
uv add package-name

# Add a dev dependency
uv add --dev package-name

# Update lockfile after manual pyproject.toml changes
uv lock
```

## Architecture & Key Components

### Core Structure
- **app/** - Main application package
  - **models.py** - SQLAlchemy models (User, Post, Community, etc.) - IMMUTABLE SCHEMA
  - **api/alpha/** - REST API implementation (Lemmy-compatible)
  - **activitypub/** - Federation implementation
  - **auth/** - Authentication (local, OAuth, passkeys)
  - **community/**, **post/**, **user/** - Feature modules
  - **shared/tasks/** - Celery background tasks
  - **templates/** - Jinja2 templates
  - **static/** - CSS, JS, images

### Key Technologies
- **Framework**: Flask 3.1.1 with Blueprints
- **Database**: PostgreSQL 13+ with SQLAlchemy ORM
- **Cache/Queue**: Redis for caching and Celery task queue
- **Background Jobs**: Celery for async processing
- **Federation**: ActivityPub protocol implementation
- **Frontend**: Server-side rendered with Jinja2, HTMX for interactivity

### Database Models Hierarchy
- **User** - User accounts with authentication
- **Community** - Discussion communities/groups
- **Post** - Link/text/image posts
- **PostReply** - Comments on posts
- **Instance** - Remote federated servers
- **Activity** - ActivityPub activities queue

## IMMUTABILITY CONSTRAINTS

**NEVER MODIFY THESE:**

1. **Database Schema**
   - NO column renames in existing tables
   - NO table renames
   - NO constraint changes (unique, foreign keys, indexes)
   - NO data type changes
   - Adding new columns is OK with proper migrations

2. **Public API Endpoints**
   - `/api/alpha/*` paths and parameters are frozen
   - Response field names cannot change
   - New optional fields can be added

3. **ActivityPub Federation**
   - `/c/{name}`, `/u/{name}`, `/post/{id}` endpoints
   - ActivityPub JSON-LD structure

## Testing Strategy

### Before ANY Changes
```bash
# Run baseline tests
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py -v
```

### After Each Change
```bash
# Test the specific area modified
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py -v

# If tests fail, revert immediately
git checkout -- <modified_files>
```

## Field Naming Consistency

The codebase uses specific field names that must remain consistent across all layers:

- Models use: `user_name`, `community_id`, `post_id`
- Forms match model field names exactly
- API schemas match model field names
- Templates reference model field names

**Always verify field names against models.py before making changes.**

## Common Development Tasks

### Adding a New Feature
1. Check existing patterns in similar modules
2. Create route in appropriate blueprint
3. Add forms if needed (following existing patterns)
4. Create/modify templates
5. Add tests
6. Run full test suite

### Modifying Templates
- Templates use Jinja2 with custom macros in `_macros.html`
- Follow existing Bootstrap 5 patterns
- Use HTMX for dynamic updates where appropriate

### Working with Federation
- ActivityPub activities are queued in the Activity table
- Background tasks process the queue
- Check `app/activitypub/` for protocol implementation

### Database Migrations
```bash
# After model changes
flask db migrate -m "descriptive message"

# Review the generated migration file
# Apply migration
flask db upgrade
```

## Important Files

- **config.py** - Application configuration
- **requirements.txt** - Python dependencies
- **.env** - Local environment variables (create from env.sample)
- **CLAUDE_CODE_WORKFLOW.md** - Detailed testing workflow
- **migrations/** - Database migration history
- **SECURITY_PATCHES.md** - Tracks fork-specific security patches (SP-###) that must survive upstream merges. Each has a regression test in `tests/security/`.

## Security Patches (SP-###)

This fork carries security patches that are not yet in upstream. They are documented in `SECURITY_PATCHES.md` and protected by regression tests in `tests/security/`.

**Before completing any upstream merge, run:**
```bash
SERVER_NAME=localhost uv run pytest tests/security/ -v
```

A failure means a patch has regressed during conflict resolution and must be re-applied. When upstream conflicts touch a patched file, **resolve in favor of the patch** unless upstream has independently fixed the same vulnerability.

## Testing Infrastructure

The repository includes comprehensive test infrastructure:
- Unit tests for models and utilities
- API endpoint tests
- Field consistency tests (CRITICAL - ensures database schema stability)
- HTML sanitization tests
- Markdown processing tests

## Production Deployment

- Uses Gunicorn WSGI server
- Celery for background tasks
- Redis for caching and task queue
- PostgreSQL for data persistence
- Docker deployment supported

## Security Considerations

- CSRF protection enabled
- SQL injection prevention via SQLAlchemy ORM
- XSS prevention through HTML sanitization
- Rate limiting on sensitive endpoints
- Proper password hashing with bcrypt

## Recent Updates & Notes

### Merge History

- Merged upstream PieFed **`v1.7.15.1`** on 2026-09-12
- Branch: `20260912/merge-upstream-v1715.1`
- Upstream commit: `29ec06f4` on upstream's **`v1.7.x` release branch**. **Upstream
  never pushed a git tag for v1.7.15.1** -- only the `VERSION` bump commit exists
  -- so `git tag`, `git ls-remote --tags` and `gh release` all still show
  `v1.7.15` as newest. Found by listing `upstream/v1.7.x` commits past the
  `v1.7.15` tag. **On future merges, check the release branch head, not just
  tags:** `git fetch upstream v1.7.x && git log --oneline <last-tag>..upstream/v1.7.x`.
  Clean linear ancestry from `v1.7.15` (5 commits, 11 files, no migrations, no
  dependency changes).
- New version: `1.7.15.1-peachpie-20260912` / `1.7.15.1+peachpie.20260912`
- Based on `main` **after** PR #103 (AI detection removal), so the merge was
  checked against the tree without those features.
- Key additions from upstream: flash on post create/edit linking back to the
  edit page; body-text heading sizes (`$h1_body`..`$h6_body`); static files get
  `Cache-Control: ... immutable` with `Vary` trimmed to `Accept-Encoding`
  (`manifest.json` excluded); topic import moves community assignment into a
  `process_topic_communities` celery task; `search_for_community` uses
  `db.session.query` so it works under `patch_db_session`; `list_communities`
  `subquery()` -> `scalar_subquery()`.
- Conflicts: 2. `app/constants.py` (version). `app/admin/util.py`
  `move_community_images_to_here`: upstream independently fixed the
  `content_type`-used-before-assignment bug this fork had fixed differently in
  2026-06; took upstream's shape (one `extra_args`, `ContentType` set per file),
  after confirming every upload path sets `ContentType` immediately before use.
- **Upstream bugs fixed rather than imported:**
  - `post_edit()` flashed
    `Markup(_('... <a href="/post/%(post_id)d/edit">Edit it</a> ...'))` **without
    passing `post_id`**. flask-babel only interpolates when kwargs are given
    (`return s if not variables else s % variables`), so it does not raise --
    every successful edit rendered a link to the literal `/post/%(post_id)d/edit`.
    The same class had sat in `protocol_handler()` since 2025-09
    (`'Failed to look up %(url)s'`, no `url=`); fixed too. Guarded by
    `tests/test_gettext_placeholders.py`, an AST scan of every `_`/`_l`/`gettext`
    call in `app/` for unfilled placeholders (allows kwargs, `**kwargs`, and
    `_(...) % {...}`).
  - **Topic import lost its communities whenever a worker was idle.**
    `create_topic_and_children()` enqueued `process_topic_communities.delay(...,
    new_topic.id)` right after `flush()`, but committed only after recursing all
    children. The task runs in its own session and writes `community.topic_id`, an
    FK to the uncommitted topic. **Verified on a throwaway Postgres 17 cluster**:
    the worker's UPDATE fails *immediately* with `community_topic_id_fkey` -- it
    does not wait for the other transaction -- and still fails after that
    transaction commits. The task rolls back and re-raises; the `do_subscribe`
    calls it already enqueued still go out. Fixed by committing before dispatch.
    Upstream's `v1.7.x` head still has the bug. Guarded by
    `tests/test_topic_import_commit_order.py` (source-level: needs two Postgres
    sessions to reproduce, which CI's SQLite cannot).
  - `num_communities` was computed right after dispatching the async task, so it
    was always 0 in production. Upstream fixed this one commit past v1.7.15.1
    (`a775d1cd`, increment inside the task); **applied verbatim** so the next
    merge sees identical lines.
  - Both guard tests were verified red against upstream's code and green after.
- **Not taken yet -- 6 further commits on `upstream/v1.7.x` past v1.7.15.1**
  (besides `a775d1cd`, applied above): `c80db570` exclude `local_only` communities from topic
  export, `bc510f8f` `RATELIMIT_ENABLED = 'False'` disables rate limiting,
  `dcb4df69` loosen daily rate limits, `9aca38fa` reduce default staff access,
  `a16922de` show roles per admin page, `4afc32f4` JS tuning. The rate-limit
  commits interact with **SP-027** (rate limiter fail-open) and deserve their own
  pass rather than riding along with a point release.
- Verification: `uvx ruff check .` clean; djlint 304 files, 0 errors; single
  migration head (no new migrations); route surface **624 -> 624, identical
  rule-by-rule**; `privacy_url` and PeachPie footer present; `tests/security/`
  **191 passed**; regression guards incl. `test_ai_detection_removed` **387
  passed**; full sweep **1 failed / 948 passed / 96 skipped** vs baseline
  1 failed / 946 passed (+2 new guards; the one failure is the known macOS-only
  `PicklingError`).
- Not verified locally: topic import end-to-end (needs Postgres + a celery worker
  + resolvable communities) and the post create/edit flash as rendered HTML.

- **2026-09-12 -- upstream's automated AI detection removed (both features)**
- Branch: `20260912/remove-ai-detection`. Not an upstream merge; removed by owner
  decision, following the anoobis precedent: delete the code, and add a guard
  test so upstream merges cannot silently bring it back.
- **1. External text detection (`DETECT_AI_ENDPOINT`, upstream since v1.6.0,
  Nov 2025).** When set, `Post.new()` / `PostReply.new()` sent the public URL of
  posts (>250 chars) and comments (>=250 chars) by recently created accounts to
  a third-party classifier. It set `ai_generated` on posts, and **auto-banned the
  user** (`user.banned = True`, no human in the loop) once 3+ scored as
  not-human at >80% confidence within 24h, tallied in a Redis sorted set
  `ai_detection:user:<id>`. It also exposed `/post/<id>/check_ai` and
  `/post_reply/<id>/check_ai` with **no authentication** (anyone logged out could
  make the server call the service for any post), which wrote the service's
  `detection_result` string into HTML **unescaped** and 500'd on a missing id.
  Removed: the config key, the `can_detect_ai` context flag, both auto-ban blocks,
  all three routes (`post_set_ai` was only reachable from `check_ai`'s output),
  both "Written by AI?" menu items and their result containers.
- **2. C2PA image inspection (upstream v1.7.13, Aug 2026).** `inspect_image_c2pa()`
  ran `c2pa-python`, a native parser, over every upload **and every remote
  image fetched for a federated post**, setting `ai_generated` when an embedded
  Content Credentials manifest claimed AI origin. Always on. Removed the
  function, both call sites, and the `c2pa-python` dependency (`uv lock` also
  dropped its transitive `toml`).
- **Kept deliberately:** the `post.ai_generated` column (immutable schema) and
  manual labelling; rows already flagged by either feature are untouched.
  The admin-toggleable **em-dash heuristic** in `PostReply.new()`
  (`enable_report_em_dash_replies`, **default on**, files an automated admin
  report for any comment containing an em dash from a new account) is a separate
  feature and was *not* removed.
- **Correction of the v1.7.15 entry below:** it said C2PA detection was "gated on
  `DETECT_AI_ENDPOINT`" and off by default, and the merge added an `env.sample`
  comment labelling `DETECT_AI_ENDPOINT` as a v1.7.15 feature. Both were wrong --
  they are unrelated, C2PA had no setting, and the endpoint dates to v1.6.0. The
  `env.sample` comment is gone and the entry is annotated in place.
- Guard: `tests/test_ai_detection_removed.py` (10 tests), which asserts the live
  `url_map` for the routes, source/templates for the setting, template flag and
  auto-ban tally, and `pyproject.toml` + `uv.lock` for the dependency. Verified
  red before removal (10 failed) and green after. Added to the merge-upstream
  skill's "Regressions that recur every merge" table. It matches identifiers, so
  a comment in `app/` naming one of these will trip it -- reword the comment.
- Verification: `uvx ruff check .` clean; djlint 304 files, 0 errors; imports
  left behind by the removal checked by hand (ruff ignores F401 here) -- `time`,
  `json`, `NOTIF_REPORT`, `get_request`, `io` all still used elsewhere;
  `tests/security/` **191 passed**; route surface **627 -> 624, exactly the 3
  AI routes removed**; the 4 edited templates compile against the real Jinja env;
  full sweep **1 failed / 946 passed / 96 skipped** (936 + the 10 new guard
  tests; the one failure is the known macOS-only `PicklingError`).
- **If production had `DETECT_AI_ENDPOINT` set**, remove it from `.env.pyfed`
  (now inert) and review users banned with an admin report from
  `reporter_user_name: 'automated'` titled "User auto-banned for AI-generated
  content".

- Merged upstream PieFed release tag `v1.7.15` on 2026-09-09
- Branch: `20260909/merge-upstream-v1715`
- Upstream tag commit: `9bb1a236` (60 commits since `0755f27f` = `v1.7.11`; clean
  linear ancestry, verified with `git merge-base --is-ancestor`)
- New version: `1.7.15-peachpie-20260909` / `1.7.15+peachpie.20260909`
- **Tag selection note:** `git tag --sort=-v:refname` puts **`v1.7.91` first** --
  it is a mis-tag from 2026-08-03 (commit `7696b0b9`, "anoobis fix"), not a
  release. The real latest is `v1.7.15`. Upstream `main` is 153 commits ahead of
  it on a separate line, as usual; we merged the **tag**, consistent with every
  merge since v1.7.0.
- Key additions from upstream:
  - **AI image detection** -- new `c2pa-python~=0.37.0` dependency,
    `inspect_image_c2pa()` in `app/utils.py`, called on uploads
    (`app/shared/post.py`) and on federated image fetches
    (`make_image_sizes_async`), setting `Post.ai_generated`. **Always on, with no
    setting.** *(This entry originally said it was gated on `DETECT_AI_ENDPOINT`
    and off by default. That was wrong: `DETECT_AI_ENDPOINT` is an unrelated
    text-detection feature dating to v1.6.0. Both were removed on 2026-09-12 --
    see the entry above.)*
  - **Admin media browser** -- `/admin/media`, `/admin/media/<file_id>/delete`,
    `/admin/media/<user_id>/delete_all` (+ a `delete_user_files_in_background`
    celery task), built on the pre-existing `user_file` association table (moved
    in `models.py`, so **no new migration**).
  - **Topic import/export** -- `/admin/topics/import|export`, `TopicImportForm`,
    `serialize_topic_tree` / `create_topic_and_children`.
  - **Instance silencing reaches comments** -- `silenced_instances()` filters
    replies for anonymous viewers; `pylova` now federates on the same batching
    fast-path as `piefed`; `User.delete_dependencies()` rewritten to purge
    `user_file` rows and ref-count avatar/cover before deleting.
  - Emoji reactions refactored into a `render_emoji_reactions()` teaser macro;
    `Post.is_event()` + `get_event_start()` Jinja global; markdown2 2.5.5 and
    beautifulsoup4 4.15; gunicorn `max_requests` 2000 -> 20000.
  - New migration: `7b8bf43fa079` (backfill NULL
    `community.total_subscriptions_count` to 0).
  - New merge migration: `merge_20260909_v1715.py` (merges
    `20260817_manual_approve_backfill` + `7b8bf43fa079`) -- single head verified
    with the alembic-based checker, which also printed the 3 revisions an
    upgrade from `merge_20260817_v1711` would apply (all additive backfills).
- **An upstream security fix we needed and took:** `ab000aa2` added
  `escape()` to `post_source()` / `post_reply_source()`, which were
  concatenating raw `post.body` / `post_reply.body` into `<pre><code>` -- a
  stored XSS reachable by anyone who could get a ```` fence into a body. It also
  added `@login_required` to both. Both files **auto-merged**, so this was found
  by reading the incoming commits, not by resolving a conflict. Verified present
  in the merged tree.
- **Upstream bugs fixed rather than imported:**
  - `Post.blocked_by_content_filter()` tokenizes the title with `re.findall(r"\w+")`
    and then tests `keyword in tokens`. A token is `\w+` by construction, so
    **any user content filter containing punctuation could never match** --
    `[Trump]`, `c++`, `covid-19`, `u.s.` were all silently inert, i.e. the filter
    failed *open* and showed the user exactly what they asked to hide. Punctuated
    keywords now match the raw lowercased title; single-word keywords keep token
    semantics so "elon" still does not match "melon".
    Upstream shipped `tests/test_content_filter.py` with a test named
    `test_content_filter_square_bracket_filter` that built the `[Trump]` filter
    and then **passed `self.content_filters` instead** -- so it duplicated the
    test above it and asserted nothing. Fixing the argument turned it red, which
    is how the bug surfaced. Guarded by two added tests in that file.
  - `app/post/util.py` called `comments.filter(PostReply.score > -20)` and
    **discarded the result** at two sites (`post_replies`, `get_comment_branch`).
    SQLAlchemy's `Query` is immutable, so the anonymous low-score cutoff had
    never applied -- logged-out visitors and crawlers saw comments below -20 that
    the feature exists to hide. Upstream added its new silencing filter directly
    above one of those lines without noticing. Both now assign; silencing was
    also mirrored into `get_comment_branch`, since otherwise a comment permalink
    or "view context" bypassed it in one click.
    Guarded by `tests/test_anonymous_reply_filters.py` (AST-based -- it detects
    a bare `.filter()` **expression statement** in the anonymous branch, so it
    catches the whole class, not just these two lines; verified to go red when
    the bug is reintroduced).
  - *(Moot since 2026-09-12, when C2PA inspection was removed.)*
    `inspect_image_c2pa()` had `import c2pa` **outside** its `try`, so a missing
    or broken c2pa build would raise straight out of `make_image_sizes_async()`
    for every federated image. Moved inside the `try`, which already returns the
    empty-manifest result on any failure.
  - Upstream's new emoji-reaction macro used single-quoted HTML attributes
    (`hx-vals='{"emoji": ...}'`), which trips this fork's `.djlintrc` H008.
    Rewritten to the fork's `&quot;`-escaped double-quoted form.
- **Deliberately not taken from upstream:**
  - `ad62c543` "api: temporarily disable file upload quota" **comments out** the
    `FILE_UPLOAD_QUOTA` check in `app/api/alpha/utils/upload.py`. Kept ours
    enforcing -- "temporarily" upstream has no expiry here, and an unbounded
    upload path on a federated instance is a storage-exhaustion vector.
  - anoobis stays removed (`env.sample`, `check_anoobis` in `app/utils.py`);
    upstream's v1.7.15 anoobis tweaks (Google exemption, Discord link previews)
    are no-ops for us. Guarded by `tests/test_anoobis_removed.py`.
  - `allowed_instance_domains()` still not carried (dead code, zero callers).
    `silenced_instances()` **was** carried -- it is load-bearing, since upstream's
    auto-merged `app/post/util.py` and `app/instance/routes.py` import it, and
    dropping it would have been an `ImportError` at startup.
  - Dockerfile (fork keeps single-stage Debian + uv + gosu + cron over upstream's
    multi-stage pip + supercronic), gunicorn `post_fork` / `post_worker_init`
    pool hooks and `timeout`/`graceful_timeout`/`keepalive`, and the fork's
    `media_library.js` DownArea polling fix (upstream's v1.7.15 change to that
    file was only removing `console.log`s and adding a 3-attempt retry -- ours
    already does 50 attempts with an idempotency guard).
- **Merged both ways with upstream, where it had independently fixed our patch:**
  - The v1.7.11 unread-comments SQL was
    `SELECT p.id AS post_id, COUNT(pr.id) ... GROUP BY p.id` read with
    `.scalar()`. `.scalar()` returns the **first column**, so `unread_comments`
    was returning the *post id*, not a count -- and our fork carried it verbatim.
    v1.7.15 drops the `p.id` column and the `GROUP BY`; taking upstream fixes a
    live bug in our tree.
  - Upstream also fixed the anonymous-branch `UnboundLocalError` we had patched,
    choosing `unread_comments = 0` where we chose `post.reply_count`. Took
    upstream's `0` rather than carry a permanent divergence in a frozen API field.
  - `RssFeed.last_error` -- upstream now assigns `utcnow()` as we did; kept only
    our extra `logger.warning` carrying the status code, which upstream drops.
- `/delete_account` resolved as a **union**, not a pick: upstream replaced the
  post-file cleanup loop with `current_user.delete_dependencies()`, but those are
  not equivalent -- ours deletes files joined via **`Post`**, upstream's via
  **`user_file`**. A post thumbnail fetched from a *remote* URL lives in
  `post_file` and never in `user_file`, so taking upstream alone would have
  quietly stopped purging those. Kept both.
- Conflicts: 19 files. `requirements.txt` deleted per policy; no `.po` conflicts.
- Verification:
  - `uvx ruff check .` -- All checks passed
  - `uv run djlint app/templates --lint` -- 304 files, 0 errors
  - `tests/security/` -- **191 passed**
  - Regression guards (`test_post_slug`, `test_ci_fixes`, `test_vote_lock_timeout`,
    `test_celery_settings`, `test_admin_api_routes_registered`,
    `test_anoobis_removed`, `test_migration_heads`, `test_api_post_list_anonymous`)
    -- **373 passed**
  - Migration heads -- **single head** (`merge_20260909_v1715`), graph fully
    connected; upgrade path from the deployed revision printed and read
  - Route surface: **622 -> 627, 5 added, 0 removed** (diffed rule-by-rule against
    a pre-merge capture -- all 5 are admin media + topic import/export)
  - Every changed template compiles against the real Jinja env from `pyfedi.py`;
    all 54 `url_for` endpoints in them resolve
  - Full sweep: **1 failed / 936 passed / 96 skipped**, against a pre-merge
    baseline of **1 failed / 922 passed / 96 skipped** -- failure list identical,
    the one failure being the known macOS-only `PicklingError` in
    `test_connection_pool_thread_safety.py` (passes on Linux CI). **Zero new
    failures.**
- **Methodology note, worth not repeating:** the first baseline run this session
  was started in the background and then `git merge` ran underneath it, so pytest
  read a tree full of conflict markers and reported 9 failures. A baseline must
  come from a tree nothing is mutating -- use `git worktree add <dir> origin/main`
  and run there.
- Not verified locally: the admin media browser (needs Postgres plus populated
  `user_file` rows). (The C2PA path was also never exercised; it has since been
  removed.)

- Merged upstream PieFed release tag `v1.7.11` on 2026-08-17
- Branch: `20260817/merge-upstream-v1711`
- Upstream tag commit: `0755f27f` (15 commits since `6e3edda1` = `v1.7.10`; clean
  linear ancestry, verified with `git merge-base --is-ancestor`)
- New version: `1.7.11-peachpie-20260817` / `1.7.11+peachpie.20260817`
- Key additions from upstream:
  - **Community RSS feeds** — `RssFeed` / `RssFeedItem` models, three
    moderator routes under `/community/`, `CommunityRssFeedEdit` /
    `DeleteCommunityRssFeedForm`, an `rss_feeds()` pass in the `cron_often`
    job that authors posts as an auto-created `feed_bot` user, and
    `RSS_FEEDS` config (**off unless set** — note any non-empty value counts as
    on, including `RSS_FEEDS=0`; documented in `env.sample`).
    New dependency `fastfeedparser~=0.6.0`. Migration `46b2b16d498b`.
  - **Follow requests** — `UserFollower.is_accepted` becomes tri-state
    (`None` = awaiting approval), `NOTIF_FOLLOW_REQUEST = 14`,
    `/user/follow_requests` + accept/reject routes, `user/notifs/14.html`,
    inbound Follows now rejected outright when the target has blocked the
    actor or their instance, and `/u/<name>/followers` only lists accepted
    followers.
  - Per-user language filtering on `/api/alpha/post/list`
    (`user_filters_languages`, cache-busted when `read_language_ids` changes);
    unread-comment counts in `post_view` variant 2 with `get_post_unread_counts`
    / `get_post_interacted_at` prefetch to avoid N+1.
  - People-browsing pages (`/instance/all|local/people`,
    `/instance/people/interesting`, `/instance/add_people` with Mastodon CSV
    import via a `bulk_follow` celery task in the new `app/instance/util.py`),
    reachable from the explore menu and the `people` search scope.
  - `flask lemmy-import` CLI command (~460 lines); blogspot.com link ban
    removed; `/post/<id>/set_read`; event edit form now shows times in the
    event's own timezone; instance-chooser search covers `elevator_pitch`;
    `'software': 'piefed'` added to the instance-chooser API payload.
  - New merge migration: `merge_20260817_v1711.py` (merges
    `20260805_local_user_uniq` + `46b2b16d498b`) — single head verified
- **Pre-existing fork gap closed while resolving `app/activitypub/routes.py`:**
  upstream renamed `user` -> `requestor_user` in the inbox `Accept`/`Reject`
  handlers back in June 2026 (`1c65524e`, shipped in v1.7.8) precisely so the
  outer `user` was no longer shadowed and an `elif user:` branch could complete
  **outbound user follows**. Our v1.7.8 merge kept `--ours` on that region, so
  the fork kept the old name and silently dropped the branch — a local user
  following a remote user never had the remote `Accept` applied, and the follow
  stayed pending forever. The tell was `UserFollowRequest` sitting in the import
  list of `app/activitypub/routes.py` with **zero uses**. Both handlers are now
  ported. Watch this pattern: an import with no uses is evidence a branch was
  dropped, not evidence of dead code.
- **Upstream bugs fixed rather than imported** (all would have shipped as-is):
  - `post_view()` assigns `unread_comments` only inside `if user_id:` but reads
    it unconditionally in the variant-2 payload — `UnboundLocalError`, i.e. a
    500 on **every anonymous `/api/alpha/post/list`**. Bound to
    `post.reply_count` on the anonymous branch (no reader, so nothing is read —
    which is also the pre-v1.7.11 value).
  - `edit_post()`'s new `flair_id` branch tests `"flair_id" in input`, but the
    RSS cron always passes the key and `RssFeed.flair_id` is nullable, so the
    default (no flair) reaches `CommunityFlair.id.in_(None)` and raises.
    Switched to a truthiness test.
  - `rss_feeds()` assigns a *string* to `RssFeed.last_error`, a `DateTime`
    column. Now logs the status code and stores a timestamp.
  - The `Accept` handler's a.gup.pe branch assigns `user` instead of
    `requestor_user`, so it both clobbers the Accept sender and always bails at
    `if not requestor_user`. The `Reject` handler's `elif user:` branch
    dereferences `join_request` without the `if join_request:` guard its
    `Accept` twin has. Both fixed.
  - `instance_banned(remote_user.instance.domain)` in the new follow-block check
    dereferences a nullable `instance` on an untrusted inbox path — guarded.
  - `app/templates/instance/people.html` uses Python `len()` in a Jinja
    expression; this fork does not expose `len` as a Jinja global, so it would
    raise at render. Replaced with `|length`
    (`tests/test_explore_page.py::test_all_templates_use_correct_length_syntax`
    catches this class).
- **Two new security patches, both upstream regressions in v1.7.11's own new
  features** (flagged by automated review after the merge commit, fixed before
  the PR merged — see `SECURITY_PATCHES.md`). Both were in files that
  *auto-merged*, which is why the conflict-resolution pass never read them:
  - **SP-028** — `user_follow_request_reject()` set `is_accepted = True`, a copy
    of the accept route, so rejecting a follow request **granted** it locally
    while sending a `Reject` to the remote server. Independently,
    `follow_requests.html` pointed the Reject button's `hx-post` at the
    *accept* endpoint. Together there was no code path by which a user could
    refuse a follower — `ap_manually_approves_followers` was a no-op that
    failed open. Test: `tests/security/test_sp028_follow_request_reject.py`.
  - **SP-029** — `community_rss_feed_edit()` / `community_rss_feed_delete()`
    authorize on `community_id` but load `RssFeed` by a globally-scoped
    `feed_id` with no ownership check, so a moderator of *any* community could
    retarget or delete another community's feed —
    `RssFeed.delete_dependencies()` also deletes every post the feed created.
    Prospective rather than historical exposure: `RSS_FEEDS` is off unless set
    and this fork has never enabled it. Test:
    `tests/security/test_sp029_rss_feed_idor.py`.
  - A third finding (SSRF via the moderator-supplied RSS feed URL) was
    **verified as already mitigated** rather than patched: the fetch goes
    through `get_request()`, and this merge deliberately kept the fork's
    SP-002 `safe_httpx_get` version over upstream's weaker
    `is_invalid_get_request_uri`. Confirmed empirically — cloud-metadata
    literals, loopback, RFC1918, non-https schemes and each redirect hop are
    all rejected. **Keeping our `get_request()` on every merge is load-bearing,
    not cosmetic.**
  - **SP-030** — `user.ap_manually_approves_followers` is nullable with no
    server default, so pre-column / non-ORM rows are NULL. v1.7.11's inbox
    handler reads it as `... is False`, making NULL mean "approve manually",
    while `follow_user()` reads `... is True` and the profile UI uses a plain
    truthiness test — three readings of one column, disagreeing only on NULL.
    A NULL user's local follows auto-accept while their remote follows queue
    invisibly in a page they never enabled. Inbox now reads `is not True`;
    migration `20260817_manual_approve_backfill` clears the NULLs for local
    users only (for remote actors NULL means "no value seen in their actor
    JSON", which is not False). Test:
    `tests/security/test_sp030_manual_approve_null.py`.
  - Lesson worth keeping: the files that need the most scrutiny after a merge
    are not the ones that conflicted. Conflicts force you to read the code;
    clean auto-merges of brand-new upstream features do not.
  - Second lesson, learned twice this session: **source-level guard tests match
    substrings, so a comment that names the thing it warns about trips its own
    guard.** It happened with `ANOOBIS` in `config.py` and again with
    `row.instance.id` in `app/cli.py`. Reword the comment; do not weaken the
    guard.
- **`flask lemmy-import` repaired** (was initially taken as-is, then fixed —
  see issue tracker). Upstream reads `row.instance_id` in the post and comment
  loops, but Lemmy's `post` and `comment` tables have no such column and the
  queries do not select one, so the command raised `AttributeError` on the
  first post — *after* having already committed the users and communities it
  imported. A post's originating instance is its author's, so a
  `person_to_instance_map` is now built during the users pass (where
  `p.instance_id` *is* selected) and used for both posts and comments.
  Upstream's `row.instance.id` on the user branch (no such relationship
  attribute) is fixed too. Guarded by `tests/test_lemmy_import_queries.py`,
  which parses every `SELECT` in the function and asserts each `row.<attr>`
  read is backed by one — catching the whole class, not just these instances.
  **Still never executed end-to-end** (needs a live Lemmy database), so treat
  it as reviewed-but-unexercised.
- Upstream's new `tests/test_api_post_list.py` is a smoke test against a
  populated database (it reads user id 1 and a remote community with posts), not
  a unit test; it fails on CI's SQLite with `no such table: user`. Given
  a `pytest.mark.skipif` with a stated reason so the skip is **visible in the
  run output** — deliberately *not* added to the `-not -name` exclusion list in
  `ci-cd.yml`, per the standing rule in this file.
- The fork's new blocks in `app/cli.py` (`lemmy_import`, `rss_feeds`) were taken
  **byte-identical to upstream**, single quotes and all, rather than reformatted.
  The repo is not actually `black`-clean (`uv run black --check` reformats
  untouched files such as `app/models.py`), so reformatting brand-new upstream
  code buys nothing and guarantees a conflict next merge. Quote style is not
  linted — `ruff.toml` selects only `E4/E7/E9/F`.
- Fork customizations preserved: hardened `ip_address()` (upstream re-added the
  forgeable `X-Forwarded-For` fallback in v1.7.11 — **not taken**; upstream's
  outside-request-context guard *was* taken, narrowed from a bare `except:` to
  `except RuntimeError`), SP-002 SSRF-guarded `get_request()`, `cached_modlist_*`
  imported from `app.shared.community` (upstream's module-level
  `from app.api.alpha.views import ...` is the exact circular import
  `tests/test_ci_fixes.py` exists to prevent), anoobis removal, `privacy_url`,
  PeachPie footer, private registration API, `uv run --no-sync` entrypoints,
  `Post.generate_ap_id` (upstream did not touch it this time),
  `app/shared/voting.py`'s `VOTE_QUOTA=0`-disables helper (so `votes_cast_today`
  is deliberately *not* imported into `app/shared/post.py`).
- Conflicts: 15 files. `requirements.txt` deleted per policy; no `.po` conflicts.
- Verification:
  - `uvx ruff check .` — All checks passed
  - `uv run djlint app/templates --lint` — 301 files, 0 errors
  - `tests/security/` — **176 passed**
  - Regression guards (`test_post_slug`, `test_ci_fixes`, `test_vote_lock_timeout`,
    `test_celery_settings`, `test_admin_api_routes_registered`,
    `test_anoobis_removed`, `test_migration_heads`) — **369 passed**
  - Migration heads — **single head** (`merge_20260817_v1711`)
  - Route surface: **611 -> 622, 11 added, 0 removed** (diffed rule-by-rule
    against a pre-merge capture, not just counted)
  - Every new/changed template compiles against the real Jinja env from
    `pyfedi.py` (not a bare `create_app`, which lacks the custom filters) and
    every `url_for` endpoint in them resolves
  - Full sweep: **1 failed / 902 passed / 96 skipped**, against a pre-merge
    baseline of **1 failed / 897 passed / 95 skipped** — failure list identical,
    the one failure being the known macOS-only `PicklingError` in
    `test_connection_pool_thread_safety.py` (passes on Linux CI). **Zero new
    failures.**
- Not verified locally: the RSS cron itself (`RSS_FEEDS` is off by default and
  exercising it needs a real feed plus Postgres) and `flask lemmy-import` (see
  above).

- **2026-08-06/07 — post-v1.7.10 follow-ups, a Dockerfile arch bug, a production
  incident, and a public-repo security audit**
- PRs #87–91, all merged. Not an upstream merge — a cleanup/hardening pass plus
  incident response, done partly during a ~5-hour GitHub Actions platform outage
  (2026-08-06, ~15:22–20:00 UTC), which forced local verification (full test
  suite, ruff, djlint, real Docker builds) in place of CI for two of the merges.
  Confirm `gh pr checks` / `git log --oneline -5` before repeating that pattern —
  it should be the exception, not habit.
- **PR #87**: `get_ip_address()`/`ip_address()` (`app/__init__.py`, `app/utils.py`)
  dropped the forgeable `X-Forwarded-For` fallback — confirmed topology is
  `client → Cloudflare → haproxy → app` (one hop, matches `ProxyFix(x_for=1)`),
  making this a real fix, not a no-op. SP-025/026/027 added to
  `SECURITY_PATCHES.md` for three fixes that shipped in the v1.7.10 cycle but
  had no bookkeeping (inert admin-API IP allowlist, forgeable-XFF admin-API
  trust, rate-limiter fail-open on Redis exception) — SP-027 also gained the
  regression test it never had. `compose.yaml` (local-dev only) fixed to build.
  3 merged worktrees removed.
- **PR #88**: `production-mirror-tests` (real Postgres 17 + Redis + Celery + web,
  required on every PR) had been reporting false-positive success since at
  least commit `457e990c` — its test-runner used bare `python -m pytest`
  against an image built `--no-dev` (no pytest installed), and the failure was
  swallowed by a trailing `echo` with no `set -e`. Fixed to `uv run pytest` +
  `set -e`. Found by actually running the script during the Actions outage
  rather than trusting the checkmark — same "measures a proxy, not behavior"
  class as the CI-exclusion-list and `pytest.skip`-swallowing bugs from
  2026-08-05.
- **PR #90 — the important one for anyone building this image locally.**
  `Dockerfile` had `FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie`.
  `$BUILDPLATFORM` is the architecture doing the build, not the target; on a
  single-stage Dockerfile this clause does nothing useful and is actively
  wrong. Invisible on GitHub's amd64 runners (`BUILDPLATFORM == TARGETPLATFORM`
  there) for this fork's entire history. Building locally on Apple Silicon with
  `docker buildx build --platform linux/amd64` produced an image whose manifest
  claimed `linux/amd64` while every binary inside was actually ARM aarch64 —
  `docker image inspect --format '{{.Architecture}}'` reported the requested
  platform correctly (it reflects what was *asked for*, not what's actually
  inside), so it looked fine locally. Only caught by extracting a binary
  (`docker cp` a container's `/usr/local/bin/python3.13`) and reading its ELF
  header directly with `file` — which doesn't execute anything, so it works
  across architectures. Silently pushed a broken image to `mikehdev/peachpie-compiled:latest`
  and `:v1.7.10-peachpie-20260806` for a window before this was caught;
  `exec format error` on the real (amd64) production host is what surfaced it.
  **If you ever build this image locally instead of via
  `docker-build-push.yml`, verify the actual architecture by extracting and
  `file`-ing a binary — never trust `docker image inspect`'s platform label
  alone when `$BUILDPLATFORM` might differ from your target.**
- **Production incident, resolved operationally (not a code change):** after
  deploying the corrected image, `/inbox` POSTs failed with
  `redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379`.
  Root cause: `RESULT_BACKEND` (`config.py`) is a **separate env var from
  `CELERY_BROKER_URL`**, required since `e170198c` (2026-05-15), defaulting to
  `redis://localhost:6379/0` if unset — and it was unset in production's real
  env file. Fixed by adding `RESULT_BACKEND` matching `CELERY_BROKER_URL`'s
  value and recreating the `pyfed`/`celery` containers. Not caused by anything
  in this session; just never surfaced until this code path was exercised.
  Worth revisiting: should `RESULT_BACKEND` default to `CELERY_BROKER_URL`
  instead of a hardcoded localhost fallback, so a missing env var degrades
  loudly (broker unreachable, worker won't start) instead of silently routing
  the result backend to nothing? Not done this session — flagging for a future
  pass, not urgent.
- **Production topology, confirmed directly (not derivable from this repo —
  the tracked `compose.yaml`/`compose.test.yml` are dev/test only and use
  different names)**: env file is `.env.pyfed` (not `.env.docker`), services
  are named `pyfed` and `celery`, Redis is `redis-pyfed`, containers are
  `pyfed-web`/`pyfed-celery` (compose project prefix `debian`, per
  `docker-compose.yml` living in `debian@theatl-services:~`). **Do not
  reconstruct production ops commands from the tracked compose files** — ask
  for the actual service/file names first. Got this wrong once this session
  (assumed `.env.docker`/`web`/`pf_network` from the repo's dev compose file)
  before being corrected.
- Also resolved: a legacy duplicate local username (`DecaturNature` /
  `decaturnature`, ids 5115/44956) blocking `20260805_local_user_uniq` on this
  instance — id 5115 was already `deleted=true, banned=true` with an
  anonymized email (`deleted_<id>@deleted.com`), so it was renamed
  (`DecaturNature_deleted_5115`) rather than the live account touched;
  `User.display_name()` returns `'[deleted]'` for any `deleted=True` row
  regardless of `user_name`, so the rename has zero UI impact. This is a
  reconciliation pattern any instance with legacy accounts may hit — see the
  migration's own error output for the inspection query.
- **Security audit for public/private repo visibility, requested and
  completed.** Full git history (not just HEAD) scanned for credentials, key
  material, and credential-shaped files — clean, nothing ever committed. CI/CD
  checked for the actual dangerous pattern (`pull_request_target`, which runs
  with secrets against untrusted fork code) — absent; the only
  secrets-touching workflow (`docker-build-push.yml`) is `workflow_dispatch`
  only. **One real finding, left unresolved by user's choice, assessed as low
  severity and not blocking**: `SECURITY_PATCHES.md`'s SP-023 entry names 16
  (actually 15 — one of the counted `post.py` sites doesn't echo
  `HX-Current-Url` into a redirect header at all, just an unrelated display
  flag) specific unpatched call sites for the same open-redirect pattern SP-023
  fixed at one site, naming `app/instance/routes.py:264` as having "no check at
  all." Publishing the exact file:line is a disclosure-risk argument, not an
  active-exploit one — the CORS-preflight reasoning in SP-023's own severity
  assessment is a property of this app's config as a whole and likely extends
  to all 15. If asked to fix these: ~10 are one-line swaps to
  `safe_hx_redirect_url()` matching the reference at `app/user/routes.py:1509`;
  ~4 (mostly `post.py`) need the helper extended to accept multiple
  `path_prefix` values (currently takes one string); 1
  (`post_reply_block_instance`) has redirect-safety logic entangled with
  unrelated business logic and needs per-site judgment, not a mechanical
  replace.
- New GitHub release: `v1.7.10-peachpie-20260806` (first release since
  `v1.7.8-peachpie-20260731`; no release had ever been cut for the v1.7.10
  line). Deployable image on Docker Hub, rebuilt via `docker-build-push.yml`
  after the PR #90 fix and verified architecture-correct (ELF header, not just
  manifest label) before this entry was written.

- **2026-08-05 — anoobis removed, and a five-month production outage found**
- On the `v1.7.10` merge branch (below), upstream's new **anoobis** proof-of-work
  gate was removed entirely rather than merged. Its proof of work was never
  verified: `anoobis.html` discarded `solveProofOfWork()`'s return value and set
  the cookie unconditionally, nothing was sent to the server, and
  `check_anoobis` only tested `request.cookies.get('anoobis') is None`. The real
  gate was "present any cookie named anoobis", which `curl -b anoobis=x`
  satisfies. It also shipped an open redirect (`furl` reports no host for
  `/\evil.com`; browsers normalise it to `//evil.com`). Guarded by
  `tests/test_anoobis_removed.py`.
- **The private-registration admin API had been dead in production since
  2026-03-06.** The v1.6.9 merge (`4c611576`) broke it two ways at once:
  1. The `from app.api.admin import routes ...` lines at the end of
     `app/api/alpha/__init__.py` were dropped. Flask registers a route only when
     its decorator executes, and nothing else imports those modules — so all 19
     endpoints 404'd for five months and six upstream merges.
  2. `admin_bp`'s `url_prefix` collapsed from `/api/alpha/admin` to `/api/alpha`.
     Upstream had independently added its *own* blueprint with the same name
     `"Admin"`; the merge kept upstream's line, and the fork's bare decorators
     (`"/private_register"`) silently relocated.
  Fixed with a dedicated `private_admin_bp`, so upstream can rename or re-prefix
  its own blueprint without moving ours. **Guarded by
  `tests/test_admin_api_routes_registered.py`, which asserts the live `url_map`.**
- **Why it hid for so long — three checks that measured a proxy, not behaviour:**
  the merge checklist verified this feature with
  `ls app/api/admin/private_registration.py` (the file was present throughout);
  `.github/workflows/ci-cd.yml` excluded 13 test files by name, quarantining ~40
  tests including the SQL-injection and private-registration security suites; and
  `test_private_registration_endpoints.py` wraps its fixture in
  `except Exception: pytest.skip(...)`, reporting "skipped" instead of "failed".
  All three now fixed. **Do not add exclusions to `ci-cd.yml` to make CI green.**
- Other genuine bugs the un-quarantined tests exposed, all fixed:
  - the IP allowlist was **inert** — it read only a `settings` row nothing ever
    writes, so `is_ip_whitelisted()` always returned `True`, while the docs told
    operators to set env vars nothing read;
  - rate limiting **failed open** on any Redis exception, and its in-memory
    fallback stored state in `flask.g` (per-request under gunicorn), so it was
    inert too — now a bounded process-local dict;
  - `get_private_registration_rate_limit()` didn't exist but was imported and
    called, so `/api/alpha/admin/health` always 400'd on `ImportError`;
  - `parse_rate_limit("5")` silently returned the default, *widening* any limit
    configured in the bare-integer form the tooling actually uses;
  - f-string SQL had regressed into `app/main/routes.py` across merges, undoing
    `d3b170f2`; now parameterized.
- Test suite: **17 failed / 496 passed / 27 errors → 1 failed / 884 passed / 0
  errors.** The remaining failure is `test_connection_pool_thread_safety.py`'s
  macOS-only `PicklingError` (spawn vs fork); it passes on Linux CI.
  `tests/conftest.py` now makes `db.create_all()` complete on SQLite — see its
  module docstring.

- Merged upstream PieFed release tag `v1.7.10` on 2026-08-05
- Branch: `20260805/merge-upstream-v1710`
- Upstream tag commit: `6e3edda1` (24 commits since `9653bed1` = `v1.7.8`; clean linear ancestry)
- New version: `1.7.10-peachpie-20260805` / `1.7.10+peachpie.20260805`
- **Branched off `20260805/celery-modern-settings`, not `main`**, so this merge
  carries the celery worker-stability work (PR #81) as well. Upstream does not
  touch the vote locks, and its `app/__init__.py` change (flask-compress)
  conflicted only against our new celery block — both were kept.
- **Note on upstream tags vs `main`:** `v1.7.10` is a release-branch tag; upstream
  `main` is 72 commits ahead of it on a separate line (`1a357b40` at merge time).
  We merged the **tag**, consistent with the v1.7.0/v1.7.8 merges. The `main`
  line carries the same anoobis/reputation work plus more.
- Key additions from upstream:
  - **Response compression** — `flask-compress`; `compress.init_app(app)` in
    `create_app()`, `COMPRESS_ALGORITHM='gzip'` (one variant only, so nginx's
    `proxy_cache` doesn't fragment), level 6, 4 KB minimum. `pyfedi.py`'s
    `after_request` switched from `headers.setdefault('Vary', ...)` to
    `response.vary.update(...)` so it merges with Flask-Compress's
    `Accept-Encoding` instead of clobbering it. Verified working: 20 KB → 54 B.
  - **"Anoobis"** proof-of-work challenge for anonymous scrapers —
    `check_anoobis` decorator in `app/utils.py`, `/anoobis` route,
    `app/templates/anoobis.html`, `ANOOBIS*` config. Applied to feed, community
    and user routes. Note the whitelist is `any(item in request.user_agent.string
    for item in [...])`, i.e. trivially bypassable by claiming to be Googlebot —
    it is a cost-imposition measure, not an access control.
  - **Author-level instance blocking on federated fetches** — `post_ap`/`comment_ap`
    return 401 when the author has blocked the requesting instance, and switch to
    `Vary: Accept, User-Agent` when the author blocks anyone. `requestor_domain()`
    derives the domain from the User-Agent, which is client-controlled, so this is
    exposure reduction, not authentication. `find_instance_id()` gained a null
    guard and `has_blocked_instance()` an `instance_id is None` guard.
  - `attributionDomains` on actor JSON (FEP-2345); `collapsible` column on
    `PostReply` + `set_collapse_post_reply()` + moderator toggle; comment-pattern
    chart on profiles; reputation system simplified (gif-reply no longer decrements
    `user.reputation`); streamlined 404/429 error pages; `(content in post body)`
    placeholder no longer rendered as a post title.
  - New migration: `8ed167b06fd7` override comment collapse
  - New merge migration: `merge_20260805_v1710.py` (merges `merge_20260730_v178`
    + `8ed167b06fd7`) — single head verified
  - New dependency: `flask-compress~=1.24` (pulls brotli/brotlicffi/backports-zstd)
- **SP-017 strengthened by upstream** (see `SECURITY_PATCHES.md`): upstream's
  `sanitize_svg_bytes` adds a 10 MB cap, strips DOCTYPE/processing instructions
  (XXE, billion laughs), and — most importantly — **removes the blanket
  `except Exception: return svg_bytes`**. Taking upstream here means the sanitizer
  now *raises* instead of returning attacker-chosen bytes unsanitized. Both
  `url_to_thumbnail_file()` call sites were updated to log and `return None`
  (drop the thumbnail) rather than fall back. The old regression test asserted
  the fail-open contract ("never raise") and was rewritten for the fail-closed
  one, plus new tests for the size cap, DOCTYPE/PI stripping, XXE rejection, and
  an AST check that the call sites don't silently reintroduce a fallback.
- Fork customizations preserved: `Post.generate_ap_id` federation-safe form
  (`tests/test_post_slug.py` green — it did **not** regress this time, the
  `models.py` auto-merge left it alone), `cached_modlist_*` function-level import
  from `app.shared.community` (circular-import fix), `privacy_url`, PeachPie
  footer, private registration API, `uv run` + `gosu` entrypoints, SP-023
  `safe_hx_redirect_url`, the `VOTE_QUOTA=0` disable comment.
- Upstream bug fixed while merging: `config.py` shipped
  `ANOOBIS_DIFFICULTY_DESKTOP = os.environ.get('') or 19` and the same for
  `_MOBILE` — an **empty env-var key**, so neither could ever be configured.
  Corrected to read their real names (and coerced to `int`).
- Gap closed while merging: our `webfinger()` was missing upstream's
  `ALLOWLIST_INTENSE` gate entirely (it had never been adopted, not deliberately
  removed). Adopted using `requestor_domain()`.
- Conflicts: 16 files. Most were the fork's double-quote/black reformatting vs
  upstream's single quotes with no semantic delta — `ruff.toml` selects only
  `E4/E7/E9/F` (not quote style), so keeping our formatting stays lint-clean.
  `requirements.txt` deleted per policy (we use `pyproject.toml`).
- Templates: `_post_full.html` kept the fork's structure (upstream's
  `is_microblog`/`microblog_header` wrapper remains deliberately deferred, see
  `ad426216`) while adopting upstream's `(content in post body)` title guard,
  matching the pattern already in `post_teaser/_macros.html`.
- Verification:
  - `uvx ruff check .` — All checks passed
  - `djlint app/templates --lint` — 297 files, 0 errors
  - `tests/security/` — 164 passed
  - `tests/test_post_slug.py` + `test_ci_fixes.py` + `test_migration_heads.py`
    + `test_vote_lock_timeout.py` + `test_celery_settings.py` — 41 passed
  - `create_app()` smoke test — boots, `/anoobis` routed, gzip active,
    `celery.conf['deprecated_settings']` is now an **empty set**
  - Full sweep: **17 failed / 520 passed / 27 errors**, failure list byte-identical
    to the pre-merge baseline (17 failed / 516 passed / 27 errors) — **zero new
    failures**; the +4 are the new SP-017 tests

- Merged upstream PieFed release tag `v1.7.8` on 2026-07-30
- Branch: `20260730/merge-upstream-v178`
- Upstream tag commit: `9653bed1` (42 commits since `a114efdc`)
- New version: `1.7.8-peachpie-20260730` / `1.7.8+peachpie.20260730`
- **Goal was complete feature parity**, so this merge also closed the API drift
  deliberately deferred on 2026-06-23 — see "API parity" below.
- Key additions from upstream:
  - Per-user community-flair blocking: `CommunityFlairBlock` model,
    `community_membership_manage` route, `EditCommunityMembership` form,
    `user_flair_unblock`, filters-page listing, `community_membership.html`
  - `PostBoost` model + `Post.post_boosts` JSON cache (microblog boosts)
  - `Post.ranking` / `ranking_scaled` Integer → Float
  - `get_deduped_post_ids(community_sql=...)` — local & popular feeds no longer
    materialize community ID lists. **Note:** our old `include_following` `noqa`
    claimed "no user_follower table in this fork"; that was stale, and taking
    upstream's version wires the follow feed up properly.
  - Federation tightening: `local_only`/`private` communities no longer federate;
    follower queries gain `is_inward=True`; Mastodon `Public` addressing drives
    microblog privacy
  - Downvotes effective again (a stray `effect = spicy_effect = 0` zeroed them)
  - Posting-pattern chart on profiles; OpenDyslexic font; `ceb` + `fil` languages
    (`tl` renamed to `fil`)
  - New migrations: `c831b9c7eee9` post_boost, `544946659eb7` float post ranking,
    `e1c6576eaa4b` block community flair
  - New merge migration: `merge_20260730_v178.py` (merges `merge_20260703_v17x`
    + `e1c6576eaa4b`)
  - **No dependency changes** — upstream `requirements.txt` was unchanged
- Fork customizations preserved:
  - `Post.generate_ap_id` keeps the federation-safe bare-community-name form.
    Upstream rewrote it again (v1.7.8: `@{community.ap_domain}`; earlier:
    `@{SERVER_NAME}`). This has now regressed on **three** consecutive merges, so
    the resolution carries an inline comment. `tests/test_post_slug.py` guards it.
    **This conflicted rather than silently auto-merging this time — keep it that way.**
  - `cached_modlist_for_community` / `cached_modlist_for_user` stay imported from
    `app.shared.community`. Upstream's `community/routes.py` imports them from
    `app.api.alpha.views` at module level, which is the exact circular import
    `tests/test_ci_fixes.py` exists to prevent.
  - Our `app/community/routes.py` constants import is a **superset** of upstream's
    (`NOTIF_POST`, `MICROBLOG_APPS`, `NOTIF_NEW_MOD`, `INVITE_*`) — keep ours.
  - PeachPie footer, `uv run` entrypoints (upstream's `sh`→`bash` shebang taken),
    `privacy_url`, private registration API.
- Grafted (closes the 2026-06-23 deferral):
  - `find_microblogging_community()` into `app/activitypub/util.py` (+ `RsaKeys`
    added to the existing signature import). Upstream's new home-feed code imports
    it at **module level**, so without the graft the app fails to start.
    Note it creates a `microblogs` Community with `user_id=1` on first local-feed
    load — verify user id 1 exists before deploying.
- **API parity (closed the standing "DEFERRED" item):** wired all 9 upstream API
  endpoints that were missing since 2026-06-23 —
  `/post/report/list`, `/post/report/resolve`, `/comment/report/resolve`,
  `/user/logout`, `/private_message/report/list`, `/private_message/report/resolve`,
  `/private_message/conversation/report{,/list,/resolve}`.
  Ported 6 functions into `utils/private_message.py` and
  `conversation_report_view` + `conversation_information_view` into `views.py`.
  Also **removed the fork's `not_yet_implemented` stub routes** for these paths —
  they sat on the plain `bp` at the same `/api/alpha` prefix as the smorest
  blueprints and would have shadowed the real routes. Upstream had already
  deleted them.
- New security patch **SP-022** (upstream regression, see `SECURITY_PATCHES.md`):
  upstream `ae1859d3` replaced `form.validate_on_submit()` in `choose_topics()`
  with a bare `request.method == 'POST'`. This fork registers **no global
  `CSRFProtect`**, so that was the endpoint's only CSRF gate. Kept upstream's
  behavioral fix, validate the token explicitly. Test:
  `tests/security/test_sp022_onboarding_csrf.py`.
- New security patch **SP-023** (upstream regression, flagged by automated review):
  upstream's `user_flair_unblock` echoes the client-controlled `HX-Current-Url` header
  into `HX-Redirect` after only `if "/user/" in curr_url`, which
  `https://evil.com/user/x` satisfies. Added `safe_hx_redirect_url()` to `app/utils.py`
  (parses the URL, rejects non-http(s) schemes, requires relative-or-exact-`request.host`,
  requires the path prefix). Low severity — a cross-origin `fetch` can't set a non-simple
  header without a CORS preflight this app never grants.
  **16 pre-existing sites remain unmigrated** across `post/`, `user/`, `chat/`,
  `instance/`, `domain/`, `community/` routes — `app/instance/routes.py:264` echoes the
  header with *no* check at all. Migrating each is a one-line change; do it as a
  dedicated pass, not inside a merge. Tracked in `SECURITY_PATCHES.md`.
- Fixed an upstream authorization bug while porting: upstream's
  `post_private_message_conversation_report` writes
  `if not (conversation or conversation.is_member(user) or user_access(...))` —
  the leading `conversation or` short-circuits the disjunction to truthy whenever
  the conversation exists, so the membership check is dead code and any
  authenticated user can report any conversation. Split existence from
  authorization. Guarded by `test_merge_v170_integration.py`.
- Dropped upstream's debug leftover in `process_new_content`:
  `if user.user_name == 'rimu': pass`.
- Upstream tests added, **rewritten as real pytest modules**: upstream's
  `tests/test_signature.py` and `tests/test_interest_parse.py` are bare scripts
  (module-level asserts, `print('Done')`, no test functions). `test_signature.py`
  taken verbatim **aborts collection of the entire suite** — every `testing_data/`
  fixture ends with a trailing newline the stored digests were never computed
  over, so its asserts fail upstream too.
- Inherited upstream WIP, noted not fixed: `process_microblog_announce()` is a stub
  that always returns `None`. Still an improvement — `resolve_remote_post()`
  dereferences `community.ap_profile_id` and would raise `AttributeError` on a
  community-less `Announce`.
- **Remaining divergence from upstream is intentional** (parity inventory went
  31 → 4): `cached_modlist_*` (our circular-import fix), `process_webfinger_request`
  (upstream refactor of logic we have inline in `webfinger()`),
  `allowed_instance_domains` (dead code — zero callers in v1.7.8), `requirements.txt`.
- Verification:
  - `uvx ruff check .`
  - `tests/security/` — 136 passed (131 + 5 new SP-022)
  - `tests/test_post_slug.py` — 11 passed
  - `tests/test_ci_fixes.py` — 8 passed
  - `tests/test_merge_v170_integration.py` — 8 passed
  - `tests/test_migration_heads.py` — 2 passed, single head
  - `djlint app/templates --lint` — 295 files, 0 errors
  - Full sweep vs `main` baseline: **0 new failures** (17 pre-existing SQLite
    fixture failures on both)
- **Local test env note:** `CACHE_DIR` defaults to `/dev/shm/pyfedi`, which does not
  exist on macOS, so tests error with `PermissionError: /dev/shm`. Run with
  `CACHE_TYPE=NullCache CACHE_REDIS_URL=memory://` as CI does.

- Merged upstream PieFed release branch `v1.7.x` on 2026-07-03
- Branch: `20260703-merge-upstream-v17x`
- Upstream branch commit: `a114efdc`
- Version unchanged: `1.7.0-peachpie-20260703` / `1.7.0+peachpie.20260703`
- Key additions from upstream release branch:
  - Follow detection now ignores inward follower rows when checking whether the local user follows another user
  - `user_follower` table now has a standalone `id` primary key and indexed follow direction/user columns
  - Slightly smaller post teaser heading typography
  - New upstream migration: `97e954045fd6_user_follow_pk.py`
  - New fork merge migration: `merge_20260703_v17x.py` (merges `merge_20260703` + `97e954045fd6`)
- Fork fix carried with this merge:
  - Restored missing web route `POST /community/<community_id>/fave`; the v1.7.0 merge had kept the template and shared helper but dropped the route, causing 404s from `/community/111/fave`
  - Added regression coverage in `tests/test_merge_v170_integration.py`
- Verification:
  - `uvx ruff check .`
  - `DATABASE_URL= SERVER_NAME=localhost uv run pytest tests/test_merge_v170_integration.py -v`
  - `DATABASE_URL= SERVER_NAME=localhost uv run pytest tests/test_ci_fixes.py -v`
  - `DATABASE_URL= SERVER_NAME=localhost uv run pytest tests/test_field_consistency_simple.py -v`
  - `DATABASE_URL= SERVER_NAME=localhost uv run pytest tests/security/ -v`
  - `DATABASE_URL= SERVER_NAME=localhost SECRET_KEY=test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxx uv run pytest tests/test_migration_heads.py -v`

- Successfully merged upstream PieFed release tag `v1.7.0` on 2026-07-03
- Branch: `20260703/merge-upstream-v170`
- Upstream tag commit: `b6f4345e` (actual `v1.7.0` release tag; not an ancestor of the prior `v1.7.0-dev` main merge)
- New version: `1.7.0-peachpie-20260703` / `1.7.0+peachpie.20260703`
- Key additions from upstream release line:
  - Vote quota enforcement (`VOTE_QUOTA`), follower/following UX and API routes, bot challenge flow, RSS token support, PM send permission flag, event location federation, wiki/post body preview tooling
  - New migrations: `c4f4625a6922_can_send_pms.py`, `1521210bd33a_bot_challenge.py`, `b9846545ef49_rss_token.py`, `7752ded50189_emoji_token_length_increase.py`
  - New merge migration: `merge_20260703.py` (merges `merge_20260623` + `7752ded50189`)
  - Dependency sync from upstream requirements into `pyproject.toml`/`uv.lock`: Flask 3.1.3, urllib3 2.7, cryptography 48, Werkzeug 3.1.8, Authlib 1.7, marshmallow 4.3, orjson 3.11, pygments 2.20
- Conflict resolution notes:
  - Kept fork Dockerfile shape (Debian slim + uv + gosu/cron), while adding upstream labels, healthcheck, and `EXPOSE`
  - Kept hardened fork security patches over upstream where stronger: signed-request SSRF guard, actor host validation, chat/PM SP-021 checks, cached modlist shared-module architecture
  - Took upstream templates for v1.7.0 UI changes, then restored fork Jinja compatibility by replacing `len(...)` with `|length`
  - Took upstream translations wholesale per merge policy
- Verification:
  - `uvx ruff check .`
  - `SERVER_NAME=localhost uv run pytest tests/test_field_consistency_simple.py -v`
  - `SERVER_NAME=localhost uv run pytest tests/security/ -v`
  - `SERVER_NAME=localhost uv run pytest tests/test_ci_fixes.py -v`

- Successfully merged with upstream PieFed (v1.7.0-dev) on 2026-06-23
- Branch: `20260623/merge-upstream-v170`
- Upstream commit: 0c4a7092 (133 commits since v1.6.24)
- Base: merged onto `20260518/upstream-security-followup` HEAD (carries SP-013/017/018/019/020/021 not yet on `main`), NOT off `main`, to preserve the security work
- New version: `1.7.0-peachpie-20260623`
- Conflict resolution strategy (fork had reformatted all files with ruff/black; upstream uses single quotes — so nearly every Python file conflicted on formatting):
  - `ruff check` only selects `E4/E7/E9/F` (NOT quote style), so taking upstream's single-quote code stays lint-clean
  - SP-patched files: took **ours** (`git checkout --ours`) to guarantee every SP-### patch survived; verified by `tests/security/` (131 pass)
  - Many upstream deltas were upstream *independently adopting our SP fixes* (SP-005 secrets token, SP-013 token rotation, SP-015 non-differential flashes, SP-017 SVG sanitize) — confirmed already present in ours
  - Non-fork files: took **theirs**; required grafts done where resolved imports demanded them: `can_upload_video(user=None)` signature, new `favorite_communities()` in utils.py (+`CommunityFavorite` import), config vars `JWT_EXPIRY_DAYS`/`BOUNCE_HOST_TYPE`/`S3_PUBLIC_ACL`
  - `shared/upload.py` taken from upstream (superset: `user=` signature + video uploads + SVG sanitize + S3 ACL)
  - Dockerfile + entrypoints kept **ours** (Debian-slim + uv + gosu + cron, not upstream's alpine/pip/supercronic)
  - Fixed two upstream lint issues: `content_type` used-before-def in `app/admin/util.py` (moved `extra_args` into the loop); dead `nsfw_count` in `app/admin/routes.py` (lines 664, 733)
- Key additions from upstream (v1.6.24 → 1.7.0-dev):
  - Allow uploading **videos** via `/api/alpha/upload/image` (#1829/#1774); `process_upload(user=...)` signature
  - Favorite communities (`CommunityFavorite` model + `favorite_communities()` jinja global; migration `5eb2bf95ed8b`)
  - Per-user follow counts (`num_following`/`num_followers`; migration `9208f044a1db`)
  - CSS variables refactor (legibility), Hacker BBS theme suite, multi-stage Docker (upstream), YunoHost docs
  - Federation robustness, anti-harassment ban notifications (`has_poster` gate), S3 public-read ACL
  - New migrations: `1adb45ab3971` topic_countries, `21ed7db16be0` allowlist_mode, `5eb2bf95ed8b` favorite_communities, `9208f044a1db` user_follow_counts, `b7d47f22842f` revoke_tokens, `e2e129221248` domain_warning_types
  - New merge migration: `merge_heads_20260623.py` (merges `merge_20260515` + `5eb2bf95ed8b`)
- **DEFERRED (follow-up):** some new upstream moderation/report API endpoints were NOT wired up, to keep the fork API layer (`api/alpha/routes.py`, `views.py`, `utils/private_message.py`) at our patched version and avoid SP-014/019/021 re-application risk. The genuinely-unrouted functions are exactly four: `get_post_report_list`, `put_post_report_resolve` (post report list+resolve), `put_reply_report_resolve` (comment report resolve), and `post_user_logout` (`user/logout` token revoke; migration `b7d47f22842f` is applied, table unused). These functions exist (auto-merged into `utils/post.py`/`reply.py`/`user.py`) but have no route in our `routes.py`. NOTE: `/comment/distinguish` and `/comment/report/list` ARE routed — they are pre-existing v1.6.21 fork endpoints, and the auto-merged util functions slot into them safely. Private-message conversation reports are also deferred (their `conversation_report_view` serializer is absent from our `views.py`). Also deferred: POP3 bounce handling in `cli.py`, `find_microblogging_community()`, `un_moderated` flag (missing deps in our tree), and the microblog-post header rendering in `app/templates/post/_post_full.html` (kept the fork version, which is djlint/`|length`-clean; upstream's version uses `len()` and single-quoted attrs that violate the fork's `.djlintrc`). NOTE: the merge's auto-merge of `models.py` silently reverted the fork's federation-safe `Post.generate_ap_id` (`/c/{community.name}/p/...`, no `@instance`) to upstream's `@SERVER_NAME` form — caught by `tests/test_post_slug.py` and re-applied; watch this on future merges. Same class of latent issue fixed for `fixup_url` (youtube `/post/` passthrough) and `microblog_content_to_link` (function-local import in models.py) — both were in `--ours` utils.py and only surfaced in CI's broad test run, not the local `create_app()` smoke test. Revisit by taking upstream for the API layer + re-applying SP-014/019/021 + circular-import re-export.

- Stable-line backport audit (2026-06-23, after the 1.7.0-dev merge): upstream `main` (1.7.0-dev) and the release tags have **diverged** — `main` is NOT the latest tagged release (which is `v1.6.27`). We deliberately track `main` per the merge-upstream skill, then audited `v1.6.24..v1.6.27` (the stable fixes since our prior base) for anything missing. Result: almost everything was already covered by our SP patches or present in `main` (b3474d19 verification-token=SP-013; redis `nx=True`=SP-011; "If an account exists"=SP-015; private-community gate=SP-014/019; secret-key check⊂SP-003; `d05b5084 sanitize svg`=SP-017; webfinger Content-Type check, PeerTube deref removal, gunicorn workers, SSRF via `ssrf_guard` all present). Only TWO federation fixes were genuinely missing and were grafted into `app/activitypub/util.py`: the `actor_json_to_model` cross-server-id guard (ada8e2ea, anti-impersonation; **hardened beyond upstream** — upstream's `server not in id` substring check is bypassable via `good.example.evil.com` / path injection, so ours parses the host and requires exact-or-subdomain match; regression test with bypass cases in `tests/test_merge_v170_integration.py`) and the nodebb mods dict-handling (c8edd293). Branch `20260623/backport-v1627-stable-fixes`.

- Successfully merged with upstream v1.6.24 on 2026-05-15
- Branch: `20260515/merge-upstream-v1624`
- Upstream commit: 3cb02f52
- Key additions from upstream (v1.6.19 → v1.6.24):
  - API authorization tightening (v1.6.19): exact `user_id` match on post edit/delete/restore; mod-status check on `move_post`
  - Performance & stability fixes; configurable read posts trimming (v1.6.19)
  - CSS fixes; plugin webhook hooks; user API improvements (v1.6.20)
  - New API endpoints: `/comment/distinguish`, `/comment/report/list` (v1.6.21)
  - Caching fixes (v1.6.21)
  - HTTP signature verification fix: removed `cache=False` from `request.get_json()` in shared_inbox; HTTP date parsing via stdlib `parsedate_to_datetime`; date comparison via `total_seconds()` (v1.6.22)
  - Ban notifications; modlog privacy; **instance silencing** feature (v1.6.23) — new migration `fbcb15c817e0_instance_silencing.py`
  - New themes: Groovebox, Quack; iOS PWA back button support (v1.6.24)
  - `ai_generated` flag in community variant-1 schema; variant-2 for `comment_report_view`
  - `community.link()` correction in Post.generate_ap_id/slug (handles remote vs local correctly)
  - Null guards for `Post.url.startswith()` and `last_active` in `posted_at_localized`
  - `reply_is_stupid` renamed to `reply_is_low_effort`
  - `plugins.fire_hook("new_local_community", community)` on local community creation
  - Per-user `page_length` override in community pagination
  - User registration / captcha API schemas added
- Restored fork customizations:
  - `privacy_url` in Site model + admin/forms.py + admin/routes.py
  - `cached_modlist_for_community/_for_user` re-export from `app.shared.community` to break the circular import (function-local import in `community/routes.py`); test_ci_fixes.py enforces this
- New migration: `merge_heads_20260515.py` (merges `merge_20260413` and `fbcb15c817e0`)
- Fixed upstream ruff errors auto-fixable: f-strings without placeholders in `app/api/alpha/utils/post.py`; unused exception variables in `app/models.py`

- Successfully merged with upstream v1.6.18 on 2026-04-13
- Branch: `20260413/merge-upstream-v1618`
- Upstream commit: 7c270694
- Key additions from upstream:
  - CronJobLog model for cron run monitoring on admin home page
  - Per-community theme disabling (`community_theme_allowed` table and user model)
  - Post list without materialized view (indexes-based approach)
  - More robust profile pic upload for users, communities, and feeds
  - Read posts table trimming after admin-configurable number of days
  - Extra fields limited to 4, with DetachedInstanceError handling
  - Private community API crash fix
  - Keyboard shortcuts page sidebar fix
  - `round_invisible_digits` none guard
  - Translatable labels in new post form and post teaser
  - New migrations: community_theme_allowed, cron_job_log, post_list_indexes
  - New migration: `merge_heads_20260413.py`
- Fixed upstream ruff errors (f-strings without placeholders, unused variable in DetachedInstanceError)

- Successfully merged with upstream v1.6.17 on 2026-04-09
- Branch: `20260409/merge-upstream-v1617`
- Upstream commit: b29aae26
- Key additions from upstream:
  - Random community feature (`/r/random`)
  - Navbar create button for posts/communities
  - Materialized view for API post list performance
  - Community themes support (`allow_community_themes` user setting)
  - Archived comments on user profiles
  - Admin instance filtering for popular communities
  - `finished_onboarding` database column
  - Caching improvements (with some reverts for stability)
  - NNTP server support
  - Dropdown menu styling improvements
  - Updated translations from Weblate
  - New dependency: `pendulum~=3.2.0`
  - New migration: `merge_heads_20260409.py`
- Fixed upstream ruff errors (f-strings without placeholders, unused variables)

- Successfully merged with upstream v1.6.12 on 2026-03-16
- Branch: `20260316/merge-upstream-v1612`

- Successfully merged with upstream v1.6.9 on 2026-03-06
- Branch: `20260306/merge-upstream-v169`
- Upstream commit: 9a4db0f4
- Key additions from upstream:
  - Admin registration approval/denial API endpoints
  - ActivityPub caching improvements (404s, longer TTLs)
  - API: join/leave feeds, modlog pagination, private voting preference
  - Inline spoiler markdown support
  - Video embedding in markdown
  - Performance: DB indexes, count(*) optimization, caching headers/etag
  - UI: user stats on home page, code block copy-to-clipboard
  - Translations: Ukrainian language, updated translations from Weblate
  - Search improvements and hang fixes
  - Private community data handling
  - S3 storage class configuration
  - `get_site_as_dict()` caching for Site object
  - User interface language preference
  - New migration: `merge_heads_20260306.py`
- Fixed upstream bugs:
  - `content_type` used before definition in `app/admin/util.py`
  - Duplicate `post_alpha_community_follow` function name in API routes
- Dependency updates for Python 3.14: orjson>=3.10.0, pillow-avif-plugin>=1.5.5

- Successfully merged with upstream v1.5.0 on 2026-01-14
- Branch: `20250723/theatl-fork-pyfed-nightly-2`
- Key additions from upstream v1.5.0:
  - Move activity type for moving posts between communities
  - Server-Sent Events (SSE) for real-time chat notifications
  - `interactionPolicy` field for quoting support
  - `cache_remote_images_locally` setting control
  - `is_bad_name()` helper for community filtering
  - `get_emoji_replacements` cache invalidation
  - Redis locking for notification handling
  - Dynamic placeholders for code stashing (`gibberish()`)
  - Bridgy-fed image handling (dict/list support)
  - Video file upload settings
  - New migration: `merge_heads_20260114.py`

- Previously merged with upstream/main (commit aa2e9e85) on 2025-08-25
- Branch: `feature/merge-upstream-20250825`
- Key additions from that merge:
  - Instance chooser functionality
  - LDAP authentication improvements
  - API enhancements (image dimensions, cross-post data)
  - New migration: `086ebbe4f31b_instance_chooser_migration.py`

### Linting & Code Quality
- Using `ruff` for Python linting (config in `ruff.toml`)
- Run `ruff check .` to verify code quality
- Fixed common issues:
  - Missing imports (e.g., `generate_password_hash` from `werkzeug.security`)
  - Indentation errors in CLI commands (must be inside `register(app)` function)

### Test Infrastructure Updates
- New test file: `tests/test_api_endpoints.py` for API validation
- Docker test environment: `compose.test.yml` and `entrypoint.test.sh`
- Production mirror testing: `./scripts/run-production-mirror-tests.sh`
- CLI commands for test setup:
  - `flask init-test-db` - Initialize test database
  - `flask load-test-fixtures` - Load test data

### Git Workflow
- Main upstream remote: `https://codeberg.org/rimu/pyfedi`
- Upstream branch to track: `main` (not `nightly`)
- Always create feature branches before merging
- Commit linting fixes before merging upstream changes
