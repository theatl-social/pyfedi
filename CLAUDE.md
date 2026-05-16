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
