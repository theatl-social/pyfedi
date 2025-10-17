# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PieFed is a federated discussion and link aggregation platform (Reddit/Lemmy/Mbin alternative) written in Python with Flask. It implements ActivityPub federation for interoperability with the fediverse.

## Critical Development Commands

### Virtual Environment Setup
```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### Running Tests
```bash
# ALWAYS activate virtual environment first
source .venv/bin/activate

# Run database schema immutability tests
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py -v

# Run specific test
SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py::test_user_model_columns_exist -v

# Run all tests in a file
SERVER_NAME=localhost python -m pytest tests/test_allowlist_html.py -v

# Run production mirror tests (Docker environment)
./scripts/run-production-mirror-tests.sh
```

### Development Server
```bash
# Set environment variables (copy env.sample to .env first)
export SERVER_NAME=localhost
export DATABASE_URL=postgresql://pyfedi:pyfedi@localhost/pyfedi

# Run Flask development server
flask run

# Run Celery worker (in separate terminal)
celery -A celery_worker.celery worker --loglevel=info
```

### Database Management
```bash
# Initialize database
flask init-db

# Create migration
flask db migrate -m "description"

# Apply migrations
flask db upgrade

# Downgrade migration
flask db downgrade
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
- Successfully merged with upstream/main (commit aa2e9e85) on 2025-08-25
- Branch: `feature/merge-upstream-20250825`
- Key additions from upstream:
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
