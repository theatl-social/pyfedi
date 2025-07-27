# PyFedi Refactoring Plan

## Overview
This document captures the comprehensive refactoring of PyFedi's ActivityPub system, including the migration from Celery to Redis Streams and the modularization of the monolithic routes.py file.

## Key Objectives
1. Replace Celery with Redis Streams + AsyncIO for better performance and reliability
2. Add comprehensive Python 3.13 type annotations throughout the codebase
3. Refactor the monolithic routes.py (2394 lines) into focused, maintainable modules
4. Maintain full API compatibility with upstream PyFedi
5. Ensure cross-platform federation compatibility (Lemmy, Mastodon, PyFedi, etc.)

## Original Routes.py Structure
The original `app/activitypub/routes.py` contained 41 route endpoints organized as follows:

### Discovery & Metadata (7 routes)
- `/.well-known/webfinger` - Actor discovery
- `/.well-known/host-meta` - Legacy host metadata
- `/.well-known/nodeinfo` - NodeInfo discovery
- `/nodeinfo/2.0[.json]` - NodeInfo 2.0 format (2 routes)
- `/nodeinfo/2.1[.json]` - NodeInfo 2.1 format (2 routes)

### API Endpoints (6 routes)
- `/api/v1/instance` - Mastodon-compatible instance info
- `/api/v1/instance/domain_blocks` - Domain block list
- `/api/is_ip_banned` - IP ban check
- `/api/is_email_banned` - Email ban check
- `/api/v3/site` - Lemmy-compatible site info
- `/api/v3/federated_instances` - Federation status

### User Actor Endpoints (3 routes)
- `/u/<actor>` - User profile
- `/u/<actor>/outbox` - User activities
- `/u/<actor>/followers` - User followers

### Community Actor Endpoints (5 routes)
- `/c/<actor>` - Community profile
- `/c/<actor>/outbox` - Community posts
- `/c/<actor>/featured` - Featured/pinned posts
- `/c/<actor>/moderators` - Moderator list
- `/c/<actor>/followers` - Community followers

### Inbox Endpoints (4 routes)
- `/inbox` - Shared inbox
- `/site_inbox` - Site-level inbox
- `/u/<actor>/inbox` - User inbox
- `/c/<actor>/inbox` - Community inbox

### Content Endpoints (4 routes)
- `/post/<int:post_id>[/]` - Post view (2 routes)
- `/post/<int:post_id>/replies` - Post replies
- `/comment/<int:comment_id>` - Comment view

### Activity Endpoints (2 routes)
- `/activities/<type>/<id>` - Individual activity lookup
- `/activity_result/<path:id>` - Activity result page

### Feed Endpoints (8 routes)
- `/f/<actor>` - Feed actor (2 routes including owner)
- `/f/<actor>/inbox` - Feed inbox
- `/f/<actor>/outbox` - Feed outbox
- `/f/<actor>/following` - Feed following
- `/f/<actor>/moderators` - Feed moderators
- `/f/<actor>/followers` - Feed followers

### Debug/Test Endpoints (2 routes)
- `/testredis` - Redis connectivity test
- Additional debug endpoints (added during refactoring)

## Refactored Module Structure

### `app/activitypub/routes/` directory
1. **webfinger.py** - Discovery endpoints (2 routes)
2. **nodeinfo.py** - Server metadata (5 routes)
3. **actors.py** - User/community profiles and collections (14 routes)
4. **inbox.py** - Receiving activities (4 routes)
5. **outbox.py** - Sending activities (functions, no routes)
6. **api.py** - Compatibility APIs (6 routes)
7. **activities.py** - Activity and feed endpoints (10 routes)
8. **debug.py** - Development tools (5 routes)
9. **helpers.py** - Shared utilities (no routes)

## Key Implementation Details

### Follow Accept/Reject Compatibility Fix
Created `format_follow_response()` function to handle different response formats:
- Lemmy/Mastodon: Simple format with just Follow ID
- PyFedi/PieFed: Detailed format with full Follow object

### Type Safety Implementation
- All functions have comprehensive type annotations
- Using Python 3.13 features (PEP 695, PEP 696)
- TypedDict for JSON structures
- Full pydoc documentation

### Redis Streams Architecture
- Priority-based queues (urgent, normal, bulk)
- Exponential backoff retry with jitter
- Dead Letter Queue for failed messages
- 24-hour TTL for completed tasks
- Consumer groups for scalability

## Migration Status
- ✅ Celery completely removed (moved to legacy folder)
- ✅ Redis Streams infrastructure implemented
- ✅ All 41 routes refactored into modules
- ✅ Type annotations added throughout
- ✅ Documentation created for each module
- ⏳ Docker entrypoint.sh creation pending
- ⏳ Web monitoring dashboard pending
- ⏳ Task scheduling implementation pending

## Verification Checklist
- [ ] All 41 original routes are implemented
- [ ] Each route has the original functionality
- [ ] Type annotations are complete
- [ ] Pydoc is comprehensive
- [ ] Cross-platform compatibility maintained
- [ ] No placeholder/TODO code remains