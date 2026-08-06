# PeachPie Release Notes

Operator- and user-facing notes for each PeachPie release. Newest first.

PeachPie is a fork of [PieFed](https://codeberg.org/rimu/pyfedi); each release
tracks an upstream PieFed release plus this fork's own patches. Version strings are
`<upstream>-peachpie-<YYYYMMDD>`.

---

## 1.7.10-peachpie-20260806

Follow-ups after yesterday's `1.7.10-peachpie-20260805` release (the upstream
v1.7.10 merge plus celery worker stability work, deployed as
`-hotfix2` — that build predates this notes file catching up; see
[SECURITY_PATCHES.md](../SECURITY_PATCHES.md) and `CLAUDE.md`'s merge history
for its full contents).

- **Client-IP resolution hardened.** `get_ip_address()` (the rate-limiter key
  function) and `ip_address()` (IP bans, country blocking, IP recorded on
  users/posts/instances) no longer fall back to a client-supplied
  `X-Forwarded-For` header. See
  [docs/TRUSTED_CLIENT_IP.md](TRUSTED_CLIENT_IP.md).
- **Admin-API security bookkeeping caught up.** SP-025/026/027 document the
  inert IP allowlist, forgeable XFF trust, and rate-limiter fail-open fixes
  that shipped in the v1.7.10 cycle but were missing from
  [SECURITY_PATCHES.md](../SECURITY_PATCHES.md); SP-027 also gained the
  automated regression test it was missing.
- **CI fix (operator-invisible):** the `production-mirror-tests` job had been
  reporting false-positive successes since at least commit `457e990c` — its
  test runner tried to run pytest from an image built without dev
  dependencies, and the failure was swallowed by a trailing `echo`. Fixed;
  doesn't affect the running application.
- **`compose.yaml` (non-production Docker Compose file) fixed** to build
  again — it referenced a Dockerfile stage this fork's single-stage image
  doesn't have. Production containers are unaffected.
- Dockerfile OCI labels now identify this as the PeachPie fork rather than
  upstream.

No database migration is required — `20260805_local_user_uniq` from
yesterday's release still applies unchanged.

---

## 1.7.8-peachpie-20260805

- **Unlimited voting is opt-in.** Set VOTE_QUOTA=0 in the web and worker
  runtime environment, then restart both services. Positive values retain the
  daily limit; an unset value remains 240. This applies to local, API, and
  inbound federated votes.
- **Profile vote totals are public.** Profiles now show aggregate upvotes and
  downvotes cast to anonymous and signed-in visitors. Individual voter lists
  and existing administrator-only metadata remain restricted.

No database migration is required.

---

## 1.7.8-peachpie-20260731

Patch release. Fixes a migration that aborted the upgrade on any database still
carrying the `post_view` materialized view — see
[the upgrade section below](#1-post-table-rewrite--plan-for-downtime). No other
changes; everything in `1.7.8-peachpie-20260730` applies unchanged.

If you never deployed `-20260730`, upgrade straight to this one and ignore the
manual `DROP` workaround.

---

## 1.7.8-peachpie-20260730

Tracks upstream PieFed **v1.7.8**. 42 upstream commits since our previous release,
`1.7.0-peachpie-20260703`.

**No dependency changes** — upstream's `requirements.txt` was unchanged, so no
`uv.lock` update is needed.

### ⚠️ Before you upgrade

Read this section. One migration takes an exclusive lock, and two changes can break
a working instance.

#### 1. `post` table rewrite — plan for downtime

Migration `544946659eb7_float_post_ranking` changes `post.ranking` and
`post.ranking_scaled` from `INTEGER` to `double precision`. In PostgreSQL this
alters the on-disk representation, so it forces a **full table rewrite under an
`ACCESS EXCLUSIVE` lock**, and both columns are indexed (`ix_post_ranking`,
`ix_post_ranking_scaled`) so **both indexes rebuild as well**.

The whole site stalls for the duration, because nothing can read `post` while the
lock is held. Duration scales with table size. Check yours first:

```sql
SELECT count(*) FROM post;
SELECT pg_size_pretty(pg_total_relation_size('post'));
```

Small instances: seconds, fine to roll live. Large instances: take a maintenance
window.

The other two migrations are cheap — `c831b9c7eee9_post_boost` and
`e1c6576eaa4b_block_community_flair` create new tables and add one nullable `JSON`
column to `post` (metadata-only on modern PostgreSQL).

**Fixed in 1.7.8-peachpie-20260731.** As originally shipped, this migration aborted
on any database still carrying the `post_view` materialized view:

```
psycopg2.errors.FeatureNotSupported: cannot alter type of a column used by a view or rule
DETAIL:  rule _RETURN on materialized view post_view depends on column "ranking"
```

PostgreSQL will not retype a column a view depends on. This fork created
`post_view` in `e44dfb9a157f` and dropped it in `8457362452d9` when the post list
moved to an indexes-based approach, but databases that were stamped or restored
from an older dump still have it. The migration now drops any leftover view first
(`IF EXISTS`, so it is a no-op otherwise). Nothing queries the view — it is derived
data — so this loses nothing.

If you are on the `-20260730` image and hit this, the upgrade rolled back cleanly
(the whole run is one transaction), so your database is untouched. Either pull
`-20260731` or later, or clear it by hand and restart:

```sql
DROP MATERIALIZED VIEW IF EXISTS post_view CASCADE;
```

Migration chain is linear with a single head, `merge_20260730_v178`.

```bash
flask db upgrade
```

#### 2. User id 1 must exist

The new local-feed code calls `find_microblogging_community()`, which creates a
`microblogs` community owned by `user_id = 1` on first load of the local feed. If
your instance has no user with id 1, that insert fails on the foreign key.

```sql
SELECT id, user_name FROM "user" WHERE id = 1;
```

#### 3. Plain-HTTP instances lose "remember me"

`REMEMBER_COOKIE_SECURE` now defaults to on (see SP-024 below). If your instance is
served over plain HTTP, remember-me stops working — users get logged out when their
session cookie expires. Either move to HTTPS (recommended) or set:

```
REMEMBER_COOKIE_SECURE = 0
```

HTTPS instances are unaffected.

### What your users will notice

- **Downvotes count again.** A bug was zeroing the downvote effect
  (`effect = spicy_effect = 0`). Existing scores are not rewritten, but ranking
  behavior changes from deploy onward — expect some visible reshuffling of "hot".
- **Profiles expose more.** The vote-quota bar now shows the **profile owner's**
  daily quota rather than the viewer's own, and a new chart shows any user's
  posting activity by hour of day over the past month. Both are visible to any
  logged-in user. Upstream's stated intent is spotting bots; some users will read
  the activity chart as surveillance, so it is worth announcing rather than
  letting people discover it.
- **The vote-quota bar is still hidden at zero.** It renders only when the counter
  is non-zero, and the counter is a Redis key namespaced by date, so it disappears
  at local midnight and after any Redis restart. Users reliably read this as "the
  vote limit was removed." It has not been — enforcement is independent of the
  display.
- **`local_only` and `private` communities no longer federate posts at all.**
  Intentional tightening upstream.
- **Microblog posts default to private** unless explicitly addressed to
  `as:Public`, affecting inbound Mastodon-style content.
- **A `microblogs` community appears**, auto-created on first local-feed load.
- **Tagalog moved from `tl` to `fil`.** There is no data migration, so users with
  `interface_language = 'tl'` fall back to the browser/default locale.
- **New OpenDyslexic font option**, and font scaling moved from `body` to `:root`,
  so custom text sizes may render slightly differently.

### New features

- **Community flair blocking** — users can hide posts carrying chosen flair, per
  community. New membership page, filters-page listing, and unblock action.
- **Post boosts** — new `post_boost` table and a `post.post_boosts` JSON cache for
  microblog boosts.
- **Faster local and popular feeds** — these no longer materialize community ID
  lists before querying.
- **Follow feed wired up.** Our previous release carried a stale comment claiming
  the `user_follower` table did not exist in this fork; it does, and the follow
  source now works.

### API

Nine endpoints that were missing from this fork since 2026-06-23 are now
available. They exist upstream and were deferred here while the API layer was
pinned to our patched version:

```
GET  /api/alpha/post/report/list                    PUT  /api/alpha/post/report/resolve
PUT  /api/alpha/comment/report/resolve              POST /api/alpha/user/logout
GET  /api/alpha/private_message/report/list         PUT  /api/alpha/private_message/report/resolve
POST /api/alpha/private_message/conversation/report
GET  /api/alpha/private_message/conversation/report/list
PUT  /api/alpha/private_message/conversation/report/resolve
```

These previously returned `{"error": "not_yet_implemented"}`. Clients that
special-cased that response should be updated.

### Security

Three fork patches in this release. Full detail in
[`SECURITY_PATCHES.md`](../SECURITY_PATCHES.md).

- **SP-022** — restored the CSRF check on onboarding topic selection. Upstream
  replaced a `validate_on_submit()` call with a bare `request.method == 'POST'`
  test; because this fork runs no global `CSRFProtect`, that left a
  state-changing endpoint with no CSRF protection.
- **SP-023** — the flair-unblock route echoed the client-controlled
  `HX-Current-Url` header into `HX-Redirect` after only a substring check, which
  `https://evil.com/user/x` satisfies.
- **SP-024** — hardened Flask-Login's remember-me cookie, which had neither the
  `Secure` flag nor an explicit `SameSite` despite being the 365-day credential.
  Because the remember cookie authenticates on its own, and browsers exempt
  cookies with no explicit `SameSite` from Lax enforcement for their first ~2
  minutes, this closed a short cross-site POST window after every login.

Also fixed while porting: an upstream authorization check on conversation
reporting was written so that its membership test could never fail, letting any
authenticated user report any conversation.

**Known and unfixed**, recorded in `SECURITY_PATCHES.md`: 133 cookie-authenticated
`POST` routes carry no per-form CSRF token and rely solely on
`SESSION_COOKIE_SAMESITE = "Lax"`. Registering `CSRFProtect` globally is the
durable fix and is planned as separate work. API routes (bearer-token only) and
ActivityPub inboxes (HTTP-signature verified) are not affected.

### Known issues inherited from upstream

- `process_microblog_announce()` ships as an unfinished stub that always returns
  `None`, so `Announce` activities arriving without a community are silently
  dropped. This is still an improvement on the previous behavior, which raised an
  `AttributeError`.
