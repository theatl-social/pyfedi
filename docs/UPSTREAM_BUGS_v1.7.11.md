# Upstream PieFed v1.7.11 — defects found during the merge

Written 2026-08-17 during the `v1.7.11` merge (upstream tag `0755f27f`).

All of them originate upstream, all are fixed in this fork, and none has been
reported to upstream — that was a deliberate call, so expect every one of these
hunks to conflict on the next merge. The regression tests are the safety net;
run them after any upstream merge.

Each is tracked as a GitHub issue on this repo. This file is the narrative
record; the issues are the tracker entries, and the two say the same thing.

| Issue | Title | Severity | Fixed in | Test |
|---|---|---|---|---|
| [#94](https://github.com/theatl-social/pyfedi/issues/94) | Anonymous `/api/alpha/post/list` returns 500 | High | `f4b57992` | — (any anonymous variant-2 render) |
| [#95](https://github.com/theatl-social/pyfedi/issues/95) | "Reject" on a follow request accepts it (SP-028) | High | `2bc4cbd2` | `tests/security/test_sp028_follow_request_reject.py` |
| [#96](https://github.com/theatl-social/pyfedi/issues/96) | IDOR on community RSS feed edit/delete (SP-029) | High | `2bc4cbd2` | `tests/security/test_sp029_rss_feed_idor.py` |
| [#97](https://github.com/theatl-social/pyfedi/issues/97) | `flask lemmy-import` reads unselected columns | Medium | `4cea2018` | `tests/test_lemmy_import_queries.py` |
| [#98](https://github.com/theatl-social/pyfedi/issues/98) | NULL `ap_manually_approves_followers` misread (SP-030) | Low | `4cea2018` | `tests/security/test_sp030_manual_approve_null.py` |
| [#99](https://github.com/theatl-social/pyfedi/issues/99) | Six smaller defects (consolidated) | Low–Medium | `f4b57992` | various |

Each section below is self-contained, which is what made it straightforward to
turn into an issue while GitHub's API was returning 503s.

---

## 1. Anonymous `/api/alpha/post/list` returns 500 (`UnboundLocalError` in `post_view`)

**Labels:** `bug`, `upstream-bug`

### Summary

v1.7.11 added unread-comment counts to `post_view()`. `unread_comments` is
assigned **only inside `if user_id:`**, but the variant-2 payload reads it
unconditionally, so every anonymous request raises `UnboundLocalError` → 500.

### Where

`app/api/alpha/views.py`, `post_view()`, variant 2:

```python
if user_id:
    ...
    if unread_counts is None:
        ...
        unread_comments = db.session.execute(...).scalar()
    else:
        unread_comments = unread_counts.get(post.id) or 0
else:
    bookmarked = post_sub = followed = read_post = False
    # unread_comments never assigned

v2 = {..., 'unread_comments': unread_comments, ...}   # UnboundLocalError
```

`get_post_list()` passes `unread_counts={}` on the anonymous path, so the
`unread_counts is None` guard does not help — the whole block is skipped.

### Impact

`/api/alpha/post/list` is a frozen public endpoint that serves logged-out
clients. On stock v1.7.11 every such request 500s. Broadest blast radius of
anything in this document: it affects any instance running v1.7.11, not just
one with an unusual configuration.

### Fix

Bind on the anonymous branch to `post.reply_count` — with no reader there is no
read state, so every comment is unread, which is also the value this field
carried before v1.7.11.

### Watch

Upstream re-touching `post_view()` will conflict here. There is no dedicated
regression test because the fix is a single assignment on a branch that any
anonymous variant-2 render exercises; a smoke request to `/api/alpha/post/list`
without an `Authorization` header is the check.

---

## 2. "Reject" on a follow request accepts it instead (SP-028)

**Labels:** `bug`, `upstream-bug`, `security`

### Summary

Two independent defects, both failing open, that together made it impossible to
refuse a follower.

1. `user_follow_request_reject()` set `is_accepted = True` — a copy of the
   accept route — so the local row recorded the follow as **granted** while a
   `Reject` activity went to the remote server. The two sides then disagree
   about whether the follow exists.
2. `app/templates/user/follow_requests.html` pointed the *Reject* button's
   `hx-post` at `user.user_follow_request_accept`, so the reject route was
   unreachable from the UI regardless.

### Impact

`ap_manually_approves_followers` exists so the account holder decides who may
follow them. Both defects removed that decision. Not remotely triggerable — it
needs the victim to click their own Reject button — so this is a broken privacy
control rather than an externally exploitable hole, but a complete one.

### Fix

`is_accepted = False`, matching `UserFollower`'s documented tri-state
(`None` pending / `True` accepted / `False` rejected), and the button retargeted
to the reject endpoint. The listing filters `is_accepted == None` so a rejected
request does not reappear as pending, and `/u/<name>/followers` filters
`is_accepted == True` so it never publishes one.

Documented as SP-028 in `SECURITY_PATCHES.md`.

---

## 3. IDOR on community RSS feed edit/delete (SP-029)

**Labels:** `bug`, `upstream-bug`, `security`

### Summary

`community_rss_feed_edit()` and `community_rss_feed_delete()` take two
independent path parameters, `community_id` and `feed_id`, and authorize on the
first only:

```python
community = Community.query.get_or_404(community_id)
if community.is_moderator() or current_user.is_admin():
    rss_feed = RssFeed.query.get_or_404(feed_id)   # ownership never checked
```

A moderator supplies a `community_id` they legitimately moderate plus any other
community's `feed_id`.

### Impact

Any authenticated moderator of **any one** community could:

- **edit** another community's feed — retargeting its URL, so the victim
  community begins publishing attacker-chosen content authored by `feed_bot`;
- **delete** it — and `RssFeed.delete_dependencies()` deletes every `Post` the
  feed ever created, so this destroys the victim community's content, not just
  its configuration.

Low bar on an open instance. Exposure is prospective rather than historical
here: `RSS_FEEDS` is off unless explicitly set, and this fork has never enabled
it.

### Fix

Both routes compare `rss_feed.community_id` against `community.id` and
`abort(404)` on a mismatch, **before any mutation**. The edit route also moved
from `RssFeed.query.get(feed_id)` to `get_or_404` — upstream's `.get()` returned
`None` for an unknown id and then assigned attributes to it (a 500).

Documented as SP-029 in `SECURITY_PATCHES.md`.

---

## 4. `flask lemmy-import` reads columns its queries do not select

**Labels:** `bug`, `upstream-bug`

### Summary

The new `lemmy-import` CLI command reads `row.instance_id` in its post and
comment loops. Lemmy's `post` and `comment` tables have no such column, and the
`SELECT` statements do not list one — so the command raises `AttributeError` on
the first post, **after** having already committed the users and communities it
imported, leaving a half-migrated database.

The user loop separately dereferenced `row.instance.id`, a relationship
attribute that does not exist on a Core result row.

### Fix

A post's originating instance is its author's. A `person_to_instance_map` is
built during the users pass — where `p.instance_id` *is* selected — and used for
both posts and comments. `row.instance.id` → `row.instance_id`.

### Test

`tests/test_lemmy_import_queries.py` parses every `SELECT` in the function and
asserts each `row.<attr>` read is backed by one, catching this whole class
rather than the two known instances.

### Caveat

**Still never executed end-to-end** — verifying it needs a live Lemmy database.
Treat as reviewed-but-unexercised.

---

## 5. NULL `ap_manually_approves_followers` read as "approve manually" (SP-030)

**Labels:** `bug`, `upstream-bug`, `security`

### Summary

`user.ap_manually_approves_followers` is `nullable=True` with **no server
default**; the model's `default=False` applies on ORM insert only, so rows
predating the column or created outside the ORM are NULL.

v1.7.11 introduced a third, inconsistent reading of the column:

| site | expression | NULL means |
|---|---|---|
| `shared/user.py` `follow_user()` | `is True` | auto-accept |
| `user/routes.py` profile UI | truthiness | auto-accept |
| `activitypub/routes.py` inbox (**v1.7.11**) | `is False` | **pending** |

### Impact

For a NULL row, local follows are accepted immediately while remote follows
queue silently in `/user/follow_requests` — a page the user has no reason to
visit, because they never turned manual approval on. Their follower count just
stops growing, with no error logged anywhere.

Fails closed, so nothing is over-shared; the problem is that it is a silent,
unlogged divergence in an access-control decision.

### Fix

The inbox now reads `is not True`, the exact complement of `follow_user()`.
Migration `20260817_manual_approve_backfill` clears the NULLs for **local users
only** (`ap_id IS NULL`) — for remote actors NULL means "no
`manuallyApprovesFollowers` seen in their actor JSON", which is not False.

Documented as SP-030 in `SECURITY_PATCHES.md`.

---

## 6. Six smaller defects fixed during the merge (consolidated)

**Labels:** `bug`, `upstream-bug`

Recorded together rather than as six issues. All fixed in `f4b57992`.

1. **`edit_post()` `flair_id` branch reaches `.in_(None)`.** It tests
   `"flair_id" in input`, but the RSS cron always passes the key and
   `RssFeed.flair_id` is nullable — so the default case (a feed with no flair,
   i.e. most of them) raises. Changed to a truthiness test.
2. **`rss_feeds()` assigns a string to `RssFeed.last_error`,** a `DateTime`
   column — blows up on commit. Now logs the status code and stores a timestamp.
3. **`Accept` handler's a.gup.pe branch assigns the wrong variable.** It sets
   `user` instead of `requestor_user`, which both clobbers the Accept sender and
   leaves `requestor_user` `None`, so the branch always bails at
   `if not requestor_user`. Introduced by upstream's June 2026 `requestor_user`
   rename (`1c65524e`).
4. **`Reject` handler dereferences `join_request` unguarded** — its `Accept`
   twin has an `if join_request:` guard; the `Reject` path does not, so a Reject
   with no matching request 500s.
5. **`instance_banned(remote_user.instance.domain)` dereferences a nullable
   `instance`** on an untrusted inbox path.
6. **`app/templates/instance/people.html` uses Python `len()` in a Jinja
   expression.** This fork does not expose `len` as a Jinja global, so the page
   would raise at render. Replaced with `|length`. Caught by
   `tests/test_explore_page.py::test_all_templates_use_correct_length_syntax`.

---

## Not filed, deliberately

- **`RSS_FEEDS = os.environ.get('RSS_FEEDS') or False`** — `RSS_FEEDS=0` yields
  the string `"0"`, which is truthy, so it *enables* the feature. Real footgun,
  but roughly ten other flags in `config.py` share the identical shape; fixing
  one in isolation would be inconsistent rather than safer. Documented in
  `env.sample` instead.
- **`/community/community/<id>/feed/...`** — the doubled path segment comes from
  upstream's decorators plus the blueprint prefix. Thirteen pre-existing routes
  in this file already do it, and templates use `url_for`, so links are correct.
  Cosmetic.
