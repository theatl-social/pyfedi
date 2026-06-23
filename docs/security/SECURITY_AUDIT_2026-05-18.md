# Security Audit — Round 4 — 2026-05-18

Targeted security audit covering Celery serialization, authorization
boundaries beyond `community_ban`, and SQL `text()` injection patterns.

**Branch:** `20260518/upstream-security-followup`
**Scope (per plan):** Part A (Celery), Part B (authz sweep), Part C (SQL sweep)
**Approach:** five parallel subagent investigations, then manual review and
patching.

## TL;DR

| Severity | Count | Patched? |
|---|---|---|
| Critical | 1 | ✅ SP-020 |
| High | 7 | ✅ SP-019, SP-020, SP-021 |
| Medium | 4 | Deferred (listed below) |
| Low | 4 | Deferred (listed below) |
| Defense-in-depth | 1 | ✅ SP-018 |

Clean areas (no findings): User notes; SQL `text()`/tsquery injection;
cross-community mod-action spillover; federation `ChatMessage` handler
(`attributedTo` spoofing); soft-delete bypass paths.

## Patched

### SP-018 — Celery serialization pinned to JSON-only (Defense-in-depth)

Celery 5.x defaults to JSON, but two paths could silently flip the default
in the future:
- `app/__init__.py` merges Flask config wholesale into `celery.conf`. A
  `CELERY_TASK_SERIALIZER` env var or `config.py` entry would be honored.
- Major-version Celery upgrades have historically changed defaults.

Unsafe legacy serializers execute arbitrary code on deserialization;
against broker messages that is RCE on every worker. Explicit allowlist:
```python
CELERY_TASK_SERIALIZER="json"
CELERY_RESULT_SERIALIZER="json"
CELERY_ACCEPT_CONTENT=["json"]
```
Regression test asserts the live `celery.conf` values plus the structural
presence of the pin in `create_app` source.

### SP-019 — `post_view` private community gate (2× High + 1× Medium + 1× Low → 1 patch)

Mirrors SP-014 (which gated `community_view`). The sibling `post_view`
function had partial coverage:

- **High**: variant 4 (`/post/like`, `/post/save`) at `app/api/alpha/views.py:455-469` returned full post body, votes, comments, polls, and cross-posts of private-community posts to non-members.
- **High**: variant 5 (resolve-object lookup-by-AP-id) at `:472-486` had the same leak via the resolve path that anonymous users hit.
- **Medium**: variant 2 had no defensive gate (called internally from list endpoints with their own SQL filter — exploitable only via composed misuse, not directly).
- **Low**: variant 3's inline gate didn't mirror `community_view`'s `user_id is None or` short-circuit (functionally equivalent but inconsistent).

Fix: single gate at the top of `post_view`, conditional on `variant in (3, 4, 5)`. Removed the inline variant-3 gate as redundant. Variants 1 and 2 stay unguarded by design — they are stub helpers whose list-endpoint callers apply community filters at the SQL level.

### SP-020 — Feeds authorization suite (1× Critical + 2× High → 1 patch)

- **Critical**: `feed_add_community` (`GET /feed/add_community`) at `app/feed/routes.py:342-369`. Read `user_id` from `request.args`, making the ownership check tautological. Any logged-in user could add or remove any community to or from any other user's feed; for public feeds, the change federated signed by the victim feed's private key.
- **High**: `make_feed` (`app/shared/feed.py:152-197`) accepted `is_instance_feed=True` from non-admins (`edit_feed` correctly gates this; creation didn't). The flag surfaces a feed in the site-wide menu — effectively a global-navigation publish-grant.
- **High**: `show_feed_rss` (`app/feed/routes.py:725-780`) had no privacy gate. The HTML sibling `show_feed` rejects non-owner/non-subscriber access on private feeds; the `.rss` path served all comers. Private feed names are enumerable because they're auto-suffixed with the owner's username.

Fixes:
1. `feed_add_community`: source `user_id` from `current_user.id`. Resolve target (and current/source) feed via `get_or_404`, abort 403 if the session user doesn't own it (admin override preserved).
2. `make_feed`: `if is_instance_feed and not user.is_admin(): is_instance_feed = False` before the `Feed(...)` constructor.
3. `show_feed_rss`: add `login_required_if_private_instance` decorator and apply the owner/subscriber gate before generating the RSS feed.

### SP-021 — Chat/DM authorization (3× High → 1 patch)

- **High**: POST `/chat/<conversation_id>` at `app/chat/routes.py:20-24` skipped the membership check — it existed only in the GET branch (line 39). Any authenticated user could POST to any conversation and inject a message.
- **High**: API `post_private_message` at `app/api/alpha/utils/private_message.py:118-138` ignored recipient blocks and `accept_private_messages` preference. The web flow and the federation `ChatMessage` handler both enforce these; only the API path bypassed them. Block bypass.
- **High**: `chat_delete` at `app/chat/routes.py:145-153` hard-deleted all `Report` rows with `suspect_conversation_id == conversation.id` whenever any member triggered the delete. A reported user could destroy their own evidence pre-review.

Fixes:
1. `chat_home` POST resolves conversation_id via `get_or_404` and aborts 403 unless `current_user.is_admin() or conversation.is_member(current_user)`.
2. `post_private_message` adds bidirectional block check and `accept_private_messages` check, mirroring `new_message` (web) and the federation path.
3. `chat_delete` branches: admins still `.delete()` the Report rows; non-admin members `.update({suspect_conversation_id: None})` instead, preserving evidence as an orphaned report row.

## Deferred (Medium and Low — to follow-up rounds)

### Medium

- **M1**: `app/api/alpha/views.py:173-408` — `post_view` variant 2 has no defensive gate. Currently safe because list-endpoint callers filter at SQL level, but defense-in-depth would lift the gate further or add explicit checks at variant 2. **Why deferred:** would require reviewing every variant-2 caller's filter to ensure no double-filtering breakage.
- **M2**: `app/feed/routes.py:214-319` — `feed_copy` lets any logged-in user clone any private feed (the form GET also pre-renders the feed's community list). **Why deferred:** Medium severity (private feeds' value is curation, not communities themselves which are public). Fix is straightforward: add a privacy gate matching `show_feed`.
- **M3**: `app/shared/feed.py:198-274` — API `post_feed`/`put_feed` accept arbitrary `parent_feed_id` without verifying ownership of the parent. A user can graft their feed under another user's feed as a child, polluting that feed's tree. **Why deferred:** low-impact UX issue rather than a data leak.
- **M4**: `app/community/routes.py:3244-3310` — community mods can `resolve`/`ignore` reports already escalated to admins (`REPORT_STATE_ESCALATED`), rescinding the escalation. **Why deferred:** medium-severity bad-faith-mod scenario; fix is a single-line status filter.

### Low

- **L1**: `app/api/alpha/views.py:432-436` — variant-3 inline gate inconsistency with `community_view`. Resolved by SP-019 lifting the gate to function top.
- **L2**: `app/community/routes.py:3236-3354` — missing `else: abort` branches on `community_moderate_report_resolve` / `_ignore`. Hardening only; current inner filter already scopes by community.
- **L3**: SQL f-string sites at `app/user/utils.py:204-228`, `app/main/routes.py:118-128`, `app/chat/routes.py:57-58`, `app/admin/util.py:198-207`, `app/cli.py:1099-1101`. All interpolate trusted values (config strings, route `<int:>`-coerced IDs, regex-gated bitstrings, `current_user.id`). No exploitable path; rewrite-with-bound-params is defense-in-depth.
- **L4**: `app/feed/routes.py:392` — dead `/feed/remove_community` UI link (route not registered).

## Clean areas (verified no findings)

### Cross-community mod-action spillover
Sweep enumerated ~40 mod-action call sites across `app/community/routes.py`,
`app/post/routes.py`, `app/shared/post.py`, `app/shared/reply.py`,
`app/shared/community.py`, `app/api/alpha/utils/community.py`,
`app/api/alpha/utils/reply.py`, `app/api/alpha/utils/post.py`. Every site
resolves a specific `Community` instance from the URL/payload then runs
`.is_moderator(user)` / `.is_owner(user)` against that instance. The
dangerous unbound `current_user.is_moderator()` pattern doesn't exist —
`User` has no `is_moderator` method; only `Community` does.

### User notes
- Write paths set `user_id=current_user.id` from session, never from form.
- Read paths filter by `UserNote.user_id == <session user id>`.
- No federation/ActivityPub exposure (`grep` in `app/activitypub/` returns zero hits).
- Admin user pages pass `user_notes=user_notes(current_user.get_id())`, not the target user's notes.
- Export and import operate on `current_user`-bound data.

### Federation ChatMessage handler
- `process_chat` in `app/activitypub/routes.py` uses the HTTP-signature-verified actor for `sender_id`, never trusts `attributedTo` (the codebase comment at line 1159 documents this).
- Recipient must be local.
- Two local users in conversation: a remote actor cannot inject because `find_existing_conversation(recipient, sender)` requires both endpoints to match.
- Block check, `accept_private_messages` check, and instance-trust check are all enforced.

### SQL `text()` / tsquery injection
~260 `text()` call sites in `app/`. All interpolated values trace to one of:
- Hardcoded constants
- `current_app.config[...]`
- Output of trusted internal helpers
- Integer-coerced values (DB IDs, `current_user.id`, route `<int:>` converters)
- Regex-gated bitstrings (`^[01]+$` for hash matching)

`sqlalchemy_searchable` `.search()` parameterizes via `to_tsquery()` — no places in the codebase build raw `to_tsquery()` strings. `ilike(f"%{q}%")` patterns bind `q` as a parameter inside `ilike()`. No injection.

### Soft-delete read paths
ChatMessage and Conversation soft-delete handling verified at the template level (`_messages.html` and API `private_message_view`). Body is substituted with "Deleted by author" rather than rendered. No bypass.

## Effort

- Part A (Celery): ~30 min — single config audit + regression test.
- Part B (authz): ~3 hours total. 4 subagents in parallel for enumeration (~10-15 min each wall-clock), then manual review and patching. Patches took the bulk of the time.
- Part C (SQL): ~25 min for the agent enumeration; ~10 min manual triage.

## Coordinated upstream follow-ups (post-embargo)

All findings in this round are not addressed upstream. Worth coordinated PRs to `rimu/pyfedi` after embargo lifts:

1. **SP-019** — post_view private gate (parallel to upstream's SP-014 equivalent).
2. **SP-020 #1** — `feed_add_community` Critical IDOR. Highest priority for upstream.
3. **SP-020 #2** — `make_feed` admin gate on `is_instance_feed`.
4. **SP-020 #3** — `show_feed_rss` privacy gate.
5. **SP-021 #1** — `chat_home` POST membership check.
6. **SP-021 #2** — API `post_private_message` block + preference enforcement.
7. **SP-021 #3** — `chat_delete` admin-only Report purge.
8. **SP-018** — Celery JSON-pin (defense-in-depth; less urgent).
9. **M4** — community mods overriding admin escalation.

## What this round did NOT cover

Per the round-4 plan, these remain for future rounds:

- WebAuthn / OAuth / LDAP authn primitives
- Markdown / HTML `| safe` end-to-end sweep
- Federation activity-type coverage (Move, Announce, Block, Flag)
- File-upload chain beyond SVG (image decoder CVEs, EXIF, MIME sniff, S3 ACL)
- Cache-poisoning sweep beyond the v1.6.22 Vary-on-cookie fix
- Stripe webhook signature verification
- Plugin hook data-flow audit
- Security headers / CSP audit
- SSE channel scoping
