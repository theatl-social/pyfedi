# Security Audit — 2026-05-15 (Round 2, Independent Re-Audit)

**Branch:** `20260515/sec-audit-round2` (sits on top of `20260515/sec-audit-findings`)
**Scope:** Independent second-opinion pass on the same branch as Round 1, with three parallel agents covering angles Round 1 didn't focus on.
**Auditors:** Three parallel Explore agents — authorization/IDOR audit, concurrency/TOCTOU audit, adversarial bypass on SP-001..SP-008.
**Status:** Embargoed — keep this report private until the disclosure window opens.

---

## TL;DR

Round 1 was thorough on the obvious vuln classes (SSRF, injection, crypto, templates, SQL, file handling, signature verification) but missed some less-obvious classes — particularly endpoint-level authorization on web routes, concurrency races in federation processing, and incomplete coverage when a single fix touched only one of multiple call sites. Round 2 found and patched **5 additional issues (SP-009..SP-013)** — 2 CRITICAL, 2 HIGH, 1 MEDIUM. Plus 4 MEDIUM/LOW deferrals.

| ID | Severity | Patched? | Where |
|---|---|---|---|
| SP-009 | CRITICAL | yes | community ban/unban auth |
| SP-010 | CRITICAL | yes | thumbnail SSRF (SP-006 follow-up) |
| SP-011 | HIGH | yes | inbox dedup TOCTOU |
| SP-012 | HIGH | yes | SECRET_KEY case-insensitive bypass |
| SP-013 | MEDIUM | yes | verification token reuse |
| F-CONC-3 | MEDIUM | deferred | password-reset replay (needs schema change) |
| F-CONC-4 | MEDIUM | deferred | actor double-create on concurrent first-fetch |
| F-CONC-5 | LOW | deferred | modlist cache stampede |
| F-BYPASS-3 | MEDIUM | deferred | SP-007 IP literal in redirect |
| F-BYPASS-4 | MEDIUM | mitigated | SP-008 1-hour replay window — partly closed by SP-011 |

---

## Methodology

Three parallel agents, each with a narrow angle Round 1 didn't deeply cover:

1. **Authorization / IDOR audit** — endpoint-level checks on web routes, especially upstream-added API endpoints (instance silencing, comment/report endpoints from v1.6.19..v1.6.24).
2. **Concurrency / TOCTOU audit** — celery task safety, federation race conditions, lock handling, account-lifecycle races.
3. **Adversarial bypass attempts** — explicitly assume each SP-001..SP-008 patch is wrong; find a way around it.

Each agent was instructed to skip findings already documented as SP-001..SP-008 and prior audit follow-ups (M-1..L-5).

---

## CRITICAL — patched (SP-009 + SP-010)

### SP-009 — Missing authorization on community ban/unban (IDOR)

- **File:** `app/community/routes.py:2235` (`community_ban_user`), `:2363` (`community_unban_user`)
- **Source:** authorization agent (confidence 10)
- **Description:** Both routes had `@login_required` and nothing more. Any authenticated user could POST to `/community/<community_id>/<user_id>/ban_user_community` and ban any other user from any community.
- **Exploit:** Attacker registers, then iterates `for community_id in range(...): for user_id in range(...): POST ban`. Effectively erases moderation across the platform until cleanup.
- **Why Round 1 missed it:** Round 1's manual sweep focused on auth-token paths, JWT, file uploads, templates, SQL — not endpoint-level role checks on individual community routes. The pattern is also subtle: the `@login_required` decorator is correct *for the platform's overall threat model* (federated discussion needs login to ban) but wrong for *who* can do it. Easy to miss without an explicit per-endpoint role-check audit.
- **Fix:** Added `if not (community.is_owner() or current_user.is_admin() or community.is_moderator()): abort(401)` immediately after the get-or-404 calls and before any state mutation. Matches the existing pattern at `community/routes.py:1773`.

### SP-010 — Thumbnail SSRF (SP-006 was incomplete)

- **File:** `app/utils.py:2797` (`url_to_thumbnail_file`)
- **Source:** bypass agent (confidence 10)
- **Description:** SP-006 patched `retrieve_metadata_of_url()` (the page-fetch) but the link-post creation flow then calls `url_to_thumbnail_file(og_image_url)` which makes a *second* HTTP request — to the og:image URL extracted from the page. The og:image URL is attacker-controlled (it's HTML they served). `url_to_thumbnail_file` called `httpx_client.get` directly with no SSRF guard.
- **Exploit:** Attacker creates a link post pointing at `https://attacker.com/`, where attacker.com returns an HTML page containing `<meta property="og:image" content="http://169.254.169.254/latest/meta-data/iam/security-credentials/">`. The thumbnail fetch hits cloud metadata; the response is stored as a "thumbnail" file the attacker can later download.
- **Why Round 1 missed it:** Round 1's whole-codebase audit verified `retrieve_metadata_of_url` was patched but didn't trace its call graph to find the *next* HTTP request. Classic single-point fix that left a sibling call unpatched. The bypass agent's adversarial framing ("assume the patch is wrong") was the right tool for catching this.
- **Fix:** Routed `url_to_thumbnail_file` through `safe_httpx_get` with the same `SSRF_GUARD_ALLOW_HTTP` / `SSRF_GUARD_ALLOW_PRIVATE` config switches.

---

## HIGH — patched (SP-011 + SP-012)

### SP-011 — Atomic SETNX dedup in shared_inbox

- **File:** `app/activitypub/routes.py:857-868`
- **Source:** concurrency agent (confidence 9)
- **Description:** Activity-ID dedup was `if redis_client.exists(id): return; redis_client.set(id, 1, ex=90)` — non-atomic. Two concurrent inbox POSTs for the same activity ID can both pass the existence check before either writes the marker.
- **Exploit:** Attacker (or a remote peer with bursty fan-out, e.g. Mastodon) sends two copies of the same Vote / Like / Announce activity to `/inbox` with microsecond timing. Both pass dedup, both call `process_inbox_request`, double-counting the vote / reputation change. Within the 90-second dedup window the bug also reduces SP-008's replay protection to "best-effort" rather than "atomic."
- **Fix:** Replaced with `if not redis_client.set(id, 1, ex=90, nx=True): return` — Redis `SET ... NX EX` is atomic at the server level; only one of N concurrent calls returns success.

### SP-012 — SECRET_KEY known-bad bypass via casing/whitespace

- **File:** `app/__init__.py:127-146` (`_validate_secret_key`)
- **Source:** bypass agent (confidence 9)
- **Description:** SP-003's known-bad list was checked with `if secret_key in known_bad`, exact-match. Inputs like `YOU-WILL-NEVER-GUESSS` (the all-caps form usually shown in docs/blog posts) or `' you-will-never-guesss '` (paste artifacts) bypassed it.
- **Exploit:** Operator copy-pastes from docs that show the example key in all-caps; validator allows boot; app is now using a known default key for Flask sessions and JWT password-reset tokens.
- **Fix:** `normalized = secret_key.strip().lower(); if normalized in known_bad: ...`. Comparison only — Flask still uses the original `secret_key` value for actual signing.

---

## MEDIUM — patched (SP-013)

### SP-013 — Email verification token cleared after first use

- **File:** `app/auth/routes.py:167-210` (`verify_email`)
- **Source:** concurrency agent (confidence 8)
- **Description:** `verify_email` set `user.verified = True` but never cleared `user.verification_token`. A captured token could be replayed against the same account.
- **Exploit narrative:** Attacker has read access to user's email (broken ESP, account compromise, browser-history, referrer-leak from a misconfigured email template that links externally). User clicks the link, gets verified. Attacker then re-uses the captured token to trigger the verify endpoint again later. With the `if user.verified` short-circuit this only re-redirects to login (limited harm), but the captured token is also a unique handle to the user's row that could be combined with other primitives — and the principle of "expire credentials on use" should be unconditional.
- **Fix:** `user.verification_token = None` set immediately before the existing commit.

---

## MEDIUM — deferred follow-ups

### F-CONC-3: Password-reset JWT replay

- **File:** `app/auth/routes.py:151-164`
- **Source:** concurrency agent (confidence 8)
- **Description:** Password reset token is a JWT carrying user_id. There's no server-side "used tokens" tracking — once issued, valid until SECRET_KEY rotates or token expires.
- **Why deferred:** proper fix needs a `PasswordResetToken` table with `is_used` + `expires_at` columns — meaningful schema change. SP-005 already made the *generation* unguessable; revocation-on-use is a separate small PR with its own review and migration.
- **Open:** add to follow-up backlog. Verify whether the JWT already carries `exp` and whether `verify_reset_password_token` enforces it; if expiry is tight enough (≤ 1 hour) the immediate risk is bounded.

### F-CONC-4: Concurrent first-time actor fetch can create duplicate Actor rows

- **Files:** `app/activitypub/routes.py:916`, `app/activitypub/util.py find_actor_or_create_cached`
- **Source:** concurrency agent (confidence 8)
- **Description:** When two activities reference an unknown remote actor concurrently, both can call `find_actor_or_create()` → `create_actor_from_remote()`, racing to insert the same actor.
- **Why deferred:** mitigated in practice by DB unique constraint on actor URL (need to verify). Worst case is an `IntegrityError` on the second insert — annoying but not exploitable. Worth a unique-constraint check + upsert-on-conflict pattern; deferred to a federation-robustness PR.

---

## MEDIUM — deferred (debatable severity)

### F-BYPASS-3: SP-007 allows numeric IP hostnames in `instance_url`

- **File:** `app/user/routes.py:12-14` (`_SAFE_INSTANCE_HOST_RE`)
- **Source:** bypass agent (confidence 8)
- **Description:** The hostname regex matches IP literals like `192.168.1.1`. Redirecting a victim to `https://192.168.1.1/...` could be used in a corporate-network phishing scenario where the attacker controls a host on the LAN.
- **Why deferred:** the threat model is narrow (attacker on victim's LAN), and the victim sees an IP literal in the address bar — not the typical phishing payoff. Round 1 explicitly removed this from the rejection list with rationale ("an IP literal in a redirect URL doesn't help phishing"). Reasonable people disagree; tracking but not patching.

### F-BYPASS-4: SP-008 1-hour replay window

- **File:** `app/activitypub/signature.py:491` (date-tolerance check)
- **Source:** bypass agent (confidence 8)
- **Description:** Precheck enforces date freshness with a 1-hour tolerance. Captured signed activities can be replayed for up to 1 hour.
- **Why partly mitigated:** SP-011 (just landed) makes the 90-second activity-ID dedup atomic, blocking replay within that window. The 90s-to-1h window remains.
- **Why deferred:** properly closing this needs either (a) shrink the date tolerance to 5-10 min and force tighter clock sync across the fediverse (operational cost), or (b) extend the dedup TTL significantly (memory cost, plus the activity ID alphabet is large enough that a determined attacker could ship many distinct IDs). Tracked.

---

## LOW — deferred

### F-CONC-5: Modlist cache stampede

- **File:** `app/shared/community.py:850-887` (cached_modlist_for_*)
- **Source:** concurrency agent (confidence 7)
- **Description:** 50-minute TTL on memoized modlists. On invalidation many concurrent requests may all re-compute. Theoretical under current code paths (the authoritative `community.is_moderator()` queries fresh DB, not the cache).
- **Why deferred:** no concrete exploit path under current call sites. Caching design improvement, not a vuln.

---

## Verification

```
SERVER_NAME=localhost uv run pytest tests/security/ -q
```

88 passed at audit time:
- 71 from Round 1 (SP-001..SP-008 + SsrfBlocked unit tests)
- 17 new from Round 2 (SP-009..SP-013)
