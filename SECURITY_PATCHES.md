# Security Patches Applied to This Fork

⚠ **Do not remove these patches during upstream merges** without verifying upstream has shipped equivalent fixes. Each patch has a regression test in `tests/security/` that will fail loudly if reverted.

If you're merging upstream and a conflict touches one of the listed files, **resolve in favor of the patch** unless upstream has independently fixed the same vulnerability.

After every upstream merge:

```bash
SERVER_NAME=localhost uv run pytest tests/security/ -v
```

Any failure means a patch has regressed and must be re-applied before the merge is considered complete.

## Patches

### SP-001 — Unsigned-activity bypass in shared_inbox

- **Disclosure:** 2026-05 (private, embargoed)
- **Files:**
  - `app/activitypub/routes.py` — `shared_inbox()` signature-verification block
  - `app/activitypub/util.py` — `verify_object_from_source()` (still used downstream of authenticated paths)
- **Test:** `tests/security/test_unsigned_activity_rejected.py`
- **Upstream status:** NOT FIXED upstream as of v1.6.24
- **Fix summary:** Removed the dict→id reduction fallback that ran when both HTTP-signature and LD-signature checks failed. Previously the code reduced `request_json['object']` (a dict with an `id`) to just the URI string, then called `verify_object_from_source()` which only checked URL-domain string equality (both attacker-controlled). Now if both signature checks fail, the request is rejected with 400.
- **Trade-off:** Legitimate cross-poster relays (a.gup.pe, PeerTube) that bounce activities now require the inner activity to be LD-signed by the original actor (which is the correct semantics anyway). If we discover legitimate flows that break, the right fix is an authenticated re-fetch (Lemmy-style) — a follow-up rather than reinstating the bypass.

### SP-002 — SSRF in outbound HTTP layer

- **Disclosure:** 2026-05 (private, embargoed)
- **Files:**
  - `app/activitypub/ssrf_guard.py` — new module: `validate_outbound_url()` and `safe_httpx_get()`
  - `app/utils.py` — `get_request()` now routes through the guard, with per-redirect validation
  - `app/activitypub/signature.py` — `HttpSignature.signed_request()` validates destination too (it bypasses `get_request()`)
- **Test:** `tests/security/test_ssrf_blocked.py`
- **Upstream status:** NOT FIXED upstream as of v1.6.24
- **Fix summary:** Every outbound HTTP request now resolves the destination hostname and refuses to proceed if any resolved IP is private, loopback, link-local, multicast, reserved, unspecified, or in the cloud-metadata literal blocklist. Redirects are followed manually with per-hop re-validation. Scheme is restricted to `https://` unless `SSRF_GUARD_ALLOW_HTTP=1` (deployment opt-in for legacy peers).
- **Known residual risk:** DNS-rebinding TOCTOU — we resolve once for validation, then httpx resolves again at fetch. Closing this fully requires a custom httpx transport that pre-resolves and dials by IP while preserving SNI. Tracked as a follow-up.
- **Dev-mode escape:** `SSRF_GUARD_ALLOW_PRIVATE=1` (used in compose dev environments where federation needs to talk to `db.local`, etc.). Never set this in production.

### SP-003 — Hardcoded SECRET_KEY fallback

- **Disclosure:** 2026-05 (private, embargoed)
- **Files:**
  - `config.py` — fallback removed
  - `app/__init__.py` — `_validate_secret_key()` runs in `create_app()` before any blueprint registration
  - `app/cli.py` — existing `config_check` command remains for ad-hoc use
- **Test:** `tests/security/test_default_secret_key_refuses_boot.py`
- **Upstream status:** NOT FIXED upstream as of v1.6.24
- **Fix summary:** `SECRET_KEY` previously fell back to the literal string `'you-will-never-guesss'` if the env var was unset, allowing any attacker who knew that string to forge Flask sessions and JWT password-reset tokens. Now there is no fallback, and the app refuses to boot if `SECRET_KEY` is missing, shorter than 32 characters, or in a small known-bad-default list.
- **Operational note:** `env.sample` should reference `SECRET_KEY` and document the 32-char minimum.

### SP-005 — Predictable token / ID generation via `random.choice`

- **Disclosure:** 2026-05 (whole-codebase audit, found post-disclosure)
- **Files:**
  - `app/auth/util.py` — `random_token()` (used for password-reset and email-verification tokens at `app/auth/util.py:267`, `app/auth/routes.py:114`, `app/admin/routes.py:1727`, `app/user/routes.py:173`, `app/cli.py:423`)
  - `app/utils.py` — `gibberish()` (used for upload filenames in `app/shared/upload.py:39` and other places)
- **Test:** `tests/security/test_sp005_crypto_randomness.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** Both functions used `random.choice` (Mersenne Twister, predictable from observed output). With ~624 observed outputs the internal state can be reconstructed and future tokens predicted. An attacker who can self-serve enough password-reset tokens (legitimate flow) can then predict reset tokens for any account → account takeover. Switched both to `secrets.choice` which reads from `os.urandom` per call.

### SP-006 — SSRF in `retrieve_metadata_of_url`

- **Disclosure:** 2026-05 (whole-codebase audit)
- **Files:**
  - `app/community/routes.py` — `retrieve_metadata_of_url()` (called from link-post creation; reads user-supplied URLs)
- **Test:** `tests/security/test_sp006_metadata_ssrf.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** Function was calling `httpx_client.get(url, follow_redirects=True)` with no SSRF guard. An attacker creating a link post could probe internal services (Redis, Postgres, cloud-metadata) by setting the link URL accordingly; the response would surface in the post title/description preview. Now routed through `safe_httpx_get`.

### SP-007 — Open redirect via `instance_url` form field

- **Disclosure:** 2026-05 (whole-codebase audit)
- **Files:**
  - `app/user/routes.py` — `fediverse_redirect()` (the `/u/<actor>/from/<instance>` flow that bounces a user to their home instance to follow a remote actor)
- **Test:** `tests/security/test_sp007_open_redirect.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** `form.instance_url.data` was interpolated into the redirect URL with no validation, allowing inputs like `evil.com/path/to/phish` or `evil.com@victim.com/...` to redirect victims off-site. Now validated against `_SAFE_INSTANCE_HOST_RE` (LDH-label hostname pattern, no scheme/path/userinfo/port).

### SP-008 — Precheck failure silently continued in `shared_inbox`

- **Disclosure:** 2026-05 (whole-codebase audit)
- **Files:**
  - `app/activitypub/routes.py` — `shared_inbox()` precheck block (~line 883-888)
- **Test:** `tests/security/test_sp008_precheck_early_return.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** When `HttpSignature.precheck` raised `VerificationFormatError` (malformed/missing digest, missing/stale date), the exception was logged but execution continued. The downstream `verify_request` call only re-checks the digest if the sender opted to include it in `signed-headers`, and does not independently re-verify date freshness, so a malformed digest could slip past. Added `return "", 400` after the precheck-failure log call.

### SP-009 — Missing authorization on community ban/unban endpoints

- **Disclosure:** 2026-05 (round-2 audit, IDOR sweep)
- **Files:**
  - `app/community/routes.py` — `community_ban_user()` and `community_unban_user()`
- **Test:** `tests/security/test_sp009_community_ban_authz.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** Both routes had only `@login_required` and no role check, so ANY authenticated user could ban or unban anyone from any community by POSTing to `/community/<id>/<uid>/ban_user_community`. Added `if not (community.is_owner() or current_user.is_admin() or community.is_moderator()): abort(401)` immediately after the get-or-404 calls and before any state mutation.

### SP-010 — SSRF in `url_to_thumbnail_file` (SP-006 incomplete)

- **Disclosure:** 2026-05 (round-2 audit, adversarial bypass on SP-006)
- **Files:**
  - `app/utils.py` — `url_to_thumbnail_file()`
- **Test:** `tests/security/test_sp010_thumbnail_ssrf.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** SP-006 wrapped `retrieve_metadata_of_url()` (the page fetch) but missed the downstream `url_to_thumbnail_file()` (the og:image fetch). An attacker creating a link post controls the og:image URL via their own page's HTML; the thumbnail fetch then bypassed the SSRF guard. Now `url_to_thumbnail_file` also routes through `safe_httpx_get`.

### SP-011 — Atomic SETNX dedup in shared_inbox (TOCTOU close)

- **Disclosure:** 2026-05 (round-2 audit, concurrency sweep)
- **Files:**
  - `app/activitypub/routes.py` — `shared_inbox()` activity-id dedup block
- **Test:** `tests/security/test_sp011_inbox_dedup_atomic.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** Activity-ID dedup used `if redis_client.exists(id): return; redis_client.set(id, 1, ex=90)` — non-atomic. Two concurrent inbox POSTs for the same activity ID could both pass the existence check before either wrote the marker, causing double-processing of votes/Likes/etc. Replaced with `redis_client.set(id, 1, ex=90, nx=True)` which is atomic at the redis-server level — exactly one caller wins.

### SP-012 — SECRET_KEY known-bad list now case- and whitespace-insensitive

- **Disclosure:** 2026-05 (round-2 audit, adversarial bypass on SP-003)
- **Files:**
  - `app/__init__.py` — `_validate_secret_key()`
- **Test:** `tests/security/test_sp012_secret_key_normalized.py`
- **Upstream status:** NOT FIXED upstream (this is on top of our SP-003)
- **Fix summary:** SP-003's known-bad set was exact-match, so `'YOU-WILL-NEVER-GUESSS'` (uppercase, the form usually shown in docs) and `' you-will-never-guesss '` (whitespace artifacts from copy-paste) bypassed the validator. Now the comparison normalizes via `.strip().lower()` before the membership check. The actual `SECRET_KEY` Flask uses is unchanged.

### SP-013 — Email verification token rotated after first use

- **Disclosure:** 2026-05 (round-2 audit, concurrency / token-replay)
- **Files:**
  - `app/auth/routes.py` — `verify_email()` (rotates token to fresh random value)
  - `app/templates/email/newsletter.html`, `newsletter.txt`, `welcome.html`, `welcome.txt` (added `{% if %}` guards around unsubscribe links)
- **Test:** `tests/security/test_sp013_verification_token_cleared.py`
- **Upstream status:** FIXED upstream in v1.6.27 (commits `f71b8259` + `b3474d19`). We adopted upstream's rotate-token approach.
- **Fix summary:** `verify_email` set `user.verified = True` but never invalidated `user.verification_token`. A captured token (email-server log, ESP cache, browser history, referrer-header leak) could be replayed against the same account. The `if user.verified` guard only catches re-execution within the *same* request; an attacker could race against a not-yet-verified account or replay later. The fix invalidates the token immediately before the commit.
- **Why rotate instead of clear:** Initial SP-013 set the token to `None`. The same column is referenced in newsletter/welcome email templates as the unsubscribe-link token; setting it to `None` caused `url_for(token=None)` to crash those sends. Upstream's later fix (b3474d19) rotates to a fresh random token, which is equivalent in security terms (the captured token is invalidated by being overwritten) but preserves the unsubscribe URLs. The four affected templates also gained `{% if %}` guards as defense-in-depth.

### SP-014 — Private community sidebar leak in `community_view`

- **Disclosure:** 2026-05 (round-3 audit; mirrors Lemmy GHSA-95q8-x6r6-672m)
- **Files:**
  - `app/api/alpha/views.py` — `community_view` precondition gate
- **Test:** `tests/security/test_sp014_private_community_leak.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** The full-info API responses (variants 3=`/community`, 4=`/community/follow`, 5=`/community/block`, 6=`resolve-object`) returned sidebar/description/banner/posting_warning/modlist for any community — including those marked `community.private = True` — without checking membership. Matches the missing check that `post_view` already enforces at line 287. Added the analogous gate at the top of `community_view` to raise an exception when a non-member queries a private community via these variants.

### SP-015 — Email-enumeration via differential flash messages

- **Disclosure:** 2026-05 (round-3 audit; mirrors Lemmy GHSA-qxrw-f6fh-34r7)
- **Files:**
  - `app/auth/routes.py` — `resend_email` and `reset_password_request`
- **Test:** `tests/security/test_sp015_email_enumeration.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** Both endpoints flashed distinct messages depending on whether the submitted email was registered (`"No user found with that email address."` vs `"Verification email sent!"`; `"No account with that email address exists"` vs `"Check your email…"`). Trivial enumeration even with rate limiting. Both branches now flash the same neutral "If an account exists, a link has been sent" message and redirect to the same path. Server-side logging unchanged.

### SP-016 — HEAD-request SSRF (SP-002 follow-up for HEAD method)

- **Disclosure:** 2026-05 (round-3 audit; mirrors Lemmy GHSA-c482-7gjx-pp36)
- **Files:**
  - `app/activitypub/ssrf_guard.py` — new `safe_httpx_head` wrapper
  - `app/utils.py` — `head_request` and `mime_type_using_head` route through the guard
- **Test:** `tests/security/test_sp016_head_request_ssrf.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** SP-002 guarded outbound GETs; HEADs (`head_request`, `mime_type_using_head`) called `httpx_client.head` directly. HEAD has no body, but an attacker can still learn port-open status, response headers (`Server`, `X-Powered-By`), and probe internal services with attacker-supplied URLs (e.g. via `is_image_url` called on community/feed/post `icon_url` / `banner_url`). Same validation as the GET wrapper, same `SSRF_GUARD_ALLOW_HTTP` / `SSRF_GUARD_ALLOW_PRIVATE` config switches.

### SP-021 — Chat/DM authorization (membership, blocks, report preservation)

- **Disclosure:** 2026-05 (round-4 audit, chat/DM surface)
- **Files:**
  - `app/chat/routes.py` — `chat_home` POST gate; `chat_delete` admin vs member branching
  - `app/api/alpha/utils/private_message.py` — `post_private_message` block + preference check
- **Test:** `tests/security/test_sp021_chat_authz.py`
- **Upstream status:** NOT FIXED upstream as of v1.6.27
- **Fix summary:** Three High-severity authz gaps in the chat/DM surface:
  1. POST `/chat/<conversation_id>` (`chat_home`) skipped the membership check — it existed only in the GET branch. Any authenticated user could inject messages into any conversation they were not part of. Now POST resolves the conversation and aborts 403 unless the actor is a member or admin.
  2. API `post_private_message` ignored bidirectional blocks and the recipient's `accept_private_messages` preference. The web `new_message` flow and the federation `ChatMessage` handler both enforce these; the API path bypassed them entirely, letting a blocked user DM the blocker via `/api/alpha/private_message`. Now mirrors the same checks.
  3. `chat_delete` previously hard-deleted all `Report` rows referencing the conversation whenever any member triggered the delete. A reported user could destroy their own evidence by deleting the conversation before staff review. Admins still purge reports; non-admin member-initiated deletes now null out `Report.suspect_conversation_id` instead, so the evidence persists as an orphan-but-readable report.

### SP-020 — Feeds authorization suite (IDOR, is_instance_feed gate, RSS privacy)

- **Disclosure:** 2026-05 (round-4 audit, feeds surface)
- **Files:**
  - `app/feed/routes.py` — `feed_add_community` IDOR fix; `show_feed_rss` privacy gate
  - `app/shared/feed.py` — `make_feed` admin gate on `is_instance_feed`
- **Test:** `tests/security/test_sp020_feed_authz.py`
- **Upstream status:** NOT FIXED upstream as of v1.6.27
- **Fix summary:** Three findings:
  1. **(Critical)** `feed_add_community` (`GET /feed/add_community`) read `user_id` from `request.args`, making the ownership check `Feed.query.get(feed_id).user_id != user_id` tautological — attacker controls both sides. Any logged-in user could add or remove communities to any other user's feed; for public feeds, the modification federated under the victim feed's private key. Now `user_id = current_user.id`; the target (and source, for moves) feed must be owned by the session user, otherwise 403. Admin override preserved.
  2. **(High)** `make_feed` accepted `is_instance_feed=True` from non-admins. The web form disables the field client-side (trivial bypass); the API has no equivalent control. `edit_feed` already admin-gates this flag; creation now matches. The flag surfaces a feed in the site-wide instance-feeds menu, so the leak let any user publish into a global navigation surface.
  3. **(High)** `show_feed_rss` had no privacy gate. The HTML sibling `show_feed` rejects non-owner/non-subscriber access on `feed.public == False`; the `.rss` path served all comers. Private feed names are auto-suffixed with the owner's username and are enumerable from public user listings. Now `show_feed_rss` is decorated with `login_required_if_private_instance` and applies the same owner/subscriber gate.

### SP-019 — Private community gate for post_view variants 3/4/5

- **Disclosure:** 2026-05 (round-4 audit, post_view surface)
- **Files:**
  - `app/api/alpha/views.py` — gate lifted to top of `post_view`, conditional on `variant in (3, 4, 5)`; inline gate in variant 3 removed as redundant
- **Test:** `tests/security/test_sp019_post_view_private.py`
- **Upstream status:** NOT FIXED upstream as of v1.6.27
- **Fix summary:** SP-014 gated `community_view` for private communities; the sibling `post_view` was left partially unprotected. Variant 4 (`/post/like`, `/post/save`) and variant 5 (resolve-object lookup-by-AP-id) had no gate — any user could fetch full post body, votes, comments, polls, and cross-posts of a private-community post by hitting these endpoints. Variant 3 had its own inline gate but didn't mirror `community_view`'s `user_id is None or` short-circuit. Fix lifts a single gate to the top of `post_view`, conditional on `variant in (3, 4, 5)`. Variants 1 and 2 remain unguarded because they are stub/internal helpers called from list endpoints whose callers apply their own SQL-level community filter.

### SP-018 — Celery serialization pinned to JSON (defense-in-depth)

- **Disclosure:** 2026-05 (round-4 audit, Celery surface)
- **Files:**
  - `app/__init__.py` — `create_app()` celery.conf.update block explicitly sets `task_serializer`, `result_serializer`, `accept_content` to JSON-only.
- **Test:** `tests/security/test_sp018_celery_json_only.py`, `tests/test_celery_settings.py`
- **Upstream status:** Not addressed upstream (Celery 5.x defaults to JSON, so neither side has an active vuln). This patch is defense-in-depth.
- **Fix summary:** Celery accepts a configurable serializer for broker messages. Unsafe legacy serializers (the p-word, yaml's default Loader) execute arbitrary code on deserialization, which against broker messages is remote code execution on every worker process. Celery 5.x defaults to JSON, but two paths could silently flip the default: a future major-version upgrade changing defaults, or the `celery.conf.update(app.config)` bulk-merge honoring a `CELERY_TASK_SERIALIZER=<unsafe>` env var. Explicit allowlist eliminates both paths.
- **2026-08-05 update:** the settings moved from the deprecated uppercase names (`CELERY_TASK_SERIALIZER`, ...) to Celery's modern lowercase names (`task_serializer`, ...), and the `celery.conf.update(app.config)` bulk-merge was removed entirely in favour of an explicit lowercase allowlist. That removal independently closes the env-var path described above — Flask config no longer reaches Celery at all — but the explicit pin is retained as the assertion that survives future refactors. See `docs/superpowers/specs/2026-08-05-celery-worker-stability-design.md`.
- **Why this matters even though no vuln is currently active:** the regression test asserts the allowlist on every test run, so any future drift fails the build loudly.

### SP-017 — SVG XSS sanitization on uploads and remote og:image fetches

- **Disclosure:** 2026-05 (upstream-discovered; adopted from upstream v1.6.27 commit `dc215422`)
- **Files:**
  - `app/utils.py` — new `sanitize_svg_bytes()` and `sanitize_svg()` helpers using `py-svg-hush~=0.3.0`
  - `app/utils.py` — `url_to_thumbnail_file()` sanitizes SVG content from remote og:image fetches
  - `app/shared/upload.py` — `process_upload()` sanitizes `.svg` uploads in place after save
  - `app/shared/post.py` — `edit_post()` image-upload branch sanitizes `.svg` in place after save
  - `pyproject.toml` — adds `py-svg-hush~=0.3.0`
- **Test:** `tests/security/test_sp017_svg_sanitize.py`
- **Upstream status:** FIXED upstream in v1.6.27. We adopted the same library and approach.
- **Fix summary:** SVG is `image/svg+xml` and renders inline. An attacker uploading an SVG with `<script>`, event handlers (`onload`, `onclick`), or `javascript:` URLs in `xlink:href` achieves persistent XSS for any user who views the SVG (community icon, user avatar, post image, og:image preview). `py-svg-hush` parses the SVG against an allowlist and strips dangerous nodes/attributes.
- **Notes:** The sanitizer is fail-closed on the *upload* path (errors return False without writing). `sanitize_svg_bytes` used to be fail-*open* — errors returned the original bytes after logging — which was justified at the time so a malformed remote SVG wouldn't break the link-preview pipeline.
- **2026-08-05 update (upstream v1.7.10, commit `5462c4ff`):** adopted upstream's hardened `sanitize_svg_bytes`. It is strictly stronger than the version we carried:
  - rejects inputs over 10 MB before parsing (parser/decompression bombs);
  - strips XML declarations (`<!...>`) and processing instructions (`<?...?>`) prior to `filter_svg`, closing XXE and billion-laughs vectors that `filter_svg` alone does not address;
  - **is now fail-CLOSED** — the blanket `except Exception: return svg_bytes` is gone. Returning attacker-chosen bytes unsanitized when the sanitizer crashed was backwards: crashing the sanitizer was itself an attack.
  Callers must therefore handle exceptions. `sanitize_svg()` already did. `url_to_thumbnail_file()` was updated at both of its call sites to log and `return None` — the thumbnail is dropped rather than persisted unsanitized. Regression tests assert the fail-closed contract *and* that the call sites do not silently reintroduce a fallback (`tests/security/test_sp017_svg_sanitize.py`).
  Note `filter_svg` re-serializes and emits its own `<?xml ...?>` declaration, so tests assert on attacker-supplied PI content rather than the absence of `<?xml`.

### SP-004 — Shell-call command injection in CLI translate command

- **Disclosure:** 2026-05 (private, embargoed) — lower severity since it requires CLI access, but still real
- **Files:**
  - `app/cli.py` — `translate init/update/compile` use `subprocess.run([...])` with list args; `init` validates `lang` against an ISO-code allowlist regex
  - `app/activitypub/util.py` — `public_key()` openssl key generation also moved to `subprocess.run`
- **Test:** `tests/security/test_cli_lang_arg_safe.py`
- **Upstream status:** NOT FIXED upstream as of v1.6.24
- **Fix summary:** The `translate init` command concatenated the `lang` CLI argument into a string passed to the legacy POSIX shell-call helper. An attacker with CLI access (or a misconfigured automation system) could inject arbitrary shell. Now the call uses `subprocess.run([...])` with list args (no shell) and validates `lang` against `^[a-z]{2,3}(_[A-Z]{2})?$` first.

### SP-022 — CSRF bypass in onboarding topic selection (upstream regression)

- **Introduced:** upstream v1.7.4 commit `ae1859d3` ("fix onboarding - topic selection"), carried in v1.7.8
- **Files:**
  - `app/auth/onboarding.py` — `choose_topics()` validates the CSRF token explicitly
- **Test:** `tests/security/test_sp022_onboarding_csrf.py`
- **Upstream status:** PRESENT upstream as of v1.7.8
- **Fix summary:** Topic selection never submitted, because `chosen_topics` is a
  `MultiCheckboxField` whose `.choices` are never populated (the template renders the
  checkboxes by hand), so `SelectMultipleField.pre_validate()` always failed and
  `form.validate_on_submit()` returned False. Upstream fixed it by replacing that call
  with a bare `request.method == 'POST'` check. This fork registers no global
  `CSRFProtect`, so `validate_on_submit()` was this endpoint's only CSRF gate; upstream's
  form leaves a state-changing POST (joining topics and their communities) with no CSRF
  protection at all. We keep upstream's behavioral fix and call
  `flask_wtf.csrf.validate_csrf()` on the submitted token, aborting 400 on failure.
- **Note:** if upstream later adopts a global `CSRFProtect`, this patch becomes redundant
  and can be reduced back to upstream's form.

### SP-023 — Open redirect via unvalidated `HX-Current-Url` echoed into `HX-Redirect`

- **Introduced:** upstream v1.7.8 `user_flair_unblock` (this fork's 2026-07-30 merge)
- **Files:**
  - `app/utils.py` — new `safe_hx_redirect_url()` validator
  - `app/user/routes.py` — `user_flair_unblock()` uses it
- **Test:** `tests/security/test_sp023_hx_redirect_open_redirect.py`
- **Upstream status:** PRESENT upstream as of v1.7.8
- **Severity:** Low — defense-in-depth, not directly exploitable through a browser.
  `HX-Current-Url` is a non-simple header, so a cross-origin `fetch` setting it triggers
  a CORS preflight, and this app only ever emits `Access-Control-Allow-Origin` (on two
  ActivityPub endpoints) and never `Access-Control-Allow-Headers`. `HX-Redirect` is then
  honored by htmx only in the origin that issued the request. Practical abuse requires
  same-origin script execution, which is already game over.
- **Fix summary:** `HX-Current-Url` is set by htmx but is an ordinary request header and
  therefore client-controlled. Upstream echoes it straight back into `HX-Redirect` after
  only a substring test (`if "/user/" in curr_url`), which `https://evil.com/user/x`
  satisfies. `safe_hx_redirect_url()` parses instead: rejects non-http(s) schemes
  (`javascript:`, `data:`), requires a relative URL or an exact `request.host` match
  (so `localhost.evil.com` fails), and requires the *path* to start with the expected
  prefix. Same bug class as SP-007.
- **KNOWN REMAINING EXPOSURE — 16 pre-existing sites not yet migrated.** This patch
  covers only the site introduced by the v1.7.8 merge. The same pattern predates it in:
  `app/post/routes.py` (8), `app/user/routes.py` (4 others), `app/chat/routes.py` (1),
  `app/instance/routes.py` (1), `app/domain/routes.py` (1), `app/community/routes.py` (1).
  **`app/instance/routes.py:264` is the worst** — it echoes `HX-Current-Url` into
  `HX-Redirect` with *no* check at all. Migrating each is a one-line change to
  `safe_hx_redirect_url()`; do it as a dedicated pass, not inside a merge.

### SP-024 — Remember-me cookie missing Secure / explicit SameSite

- **Origin:** pre-existing in this fork and upstream; not introduced by any merge
- **Files:**
  - `config.py` — `REMEMBER_COOKIE_SECURE` / `_HTTPONLY` / `_SAMESITE` now set explicitly
  - `env.sample` — documents the `*_SECURE` override for local HTTP development
- **Test:** `tests/security/test_sp024_remember_cookie_flags.py`
- **Upstream status:** PRESENT upstream as of v1.7.8
- **Fix summary:** Flask-Login configures its remember-me cookie separately from Flask's
  session cookie, and its library defaults are weaker — `flask_login/config.py` ships
  `COOKIE_SECURE = False` and `COOKIE_SAMESITE = None`, which `login_manager.py:472-474`
  reads via `config.get("REMEMBER_COOKIE_*", <library default>)`. This fork set
  `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE` but never the `REMEMBER_COOKIE_*` equivalents,
  so the **long-lived** credential was the weak one: `app/auth/routes.py` calls
  `login_user(user, remember=True)` on every login and the cookie lasts 365 days, yet it
  carried no `Secure` flag (transmissible over plain HTTP) and no explicit `SameSite`.
  Now mirrors the session cookie.
- **Why explicit SameSite matters:** an omitted attribute leans on browser defaults.
  Modern browsers treat that as Lax, but Chrome's "Lax+POST" intervention grants a
  ~2 minute cross-site POST window to cookies with no explicit `SameSite` — which is
  the layer the CSRF posture below depends on.
- **Deployment note:** `REMEMBER_COOKIE_SECURE` defaults to on. A deployment served over
  plain HTTP will stop honoring remember-me until it sets `REMEMBER_COOKIE_SECURE=0`
  (documented in `env.sample`) or, preferably, moves to HTTPS.
- **RELATED, NOT FIXED — CSRF depends on a single layer.** 133 cookie-authenticated POST
  routes carry no per-form CSRF token, including `admin_user_delete`,
  `admin_community_delete`, `admin_approve_registrations_approve`, `post_purge` and
  `delete_profile`. There is no global `CSRFProtect`; the only thing preventing
  cross-site forgery is `SESSION_COOKIE_SAMESITE = "Lax"`. That is real protection in
  current browsers but has no defense in depth behind it, and `Lax` is same-*site*, not
  same-*origin* — a subdomain can still POST with cookies. Registering `CSRFProtect`
  globally is the durable fix and is a dedicated piece of work.
  (Not affected: the ~70 `/api/alpha/*` routes authenticate by bearer token only —
  `authorise_api_user` reads solely the `Authorization` header, with no cookie fallback —
  and the 9 ActivityPub inboxes are HTTP-signature verified under SP-001.)

### SP-025 — Admin API IP allowlist was inert (read a settings row nothing ever wrote)

- **Origin:** pre-existing in this fork; the private-registration admin API's IP
  allowlist never functioned as documented
- **Files:**
  - `app/utils.py` — `get_private_registration_allowed_ips()` now reads
    `PRIVATE_REGISTRATION_IPS` / `PRIVATE_REGISTRATION_ALLOWED_IPS` from the
    environment first, falling back to the settings row
- **Test:** `tests/security/test_admin_ip_allowlist.py`
- **Upstream status:** N/A — fork-only feature (private registration admin
  API), no upstream equivalent
- **Severity:** the allowlist is one of four gates in front of an
  account-provisioning API (alongside the shared secret,
  `PRIVATE_REGISTRATION_ENABLED`, and rate limiting — see SP-027); with this
  gate inert, an attacker holding the shared secret faced three, not four.
- **Fix summary:** `get_private_registration_allowed_ips()` read only
  `get_setting("PRIVATE_REGISTRATION_IPS")` — a row in the `settings` table
  that no CLI command, admin route, or startup path ever wrote. The list was
  therefore always empty, and `is_ip_whitelisted()` treats an empty list as "no
  restriction configured," returning `True` for every address — while
  `docs/PRIVATE_REGISTRATION_TESTING.md` and `ADMIN_API.md` told operators to
  configure it through environment variables nothing read.

### SP-026 — Forgeable `X-Forwarded-For` trusted for client-IP resolution

- **Origin:** pre-existing in this fork and upstream for the app-wide
  `get_ip_address()` / `ip_address()`; the admin-API instance was introduced
  with the private registration feature
- **Files:**
  - `app/api/admin/security.py` — `validate_private_registration_request()`
    now reads `request.remote_addr`
  - `app/__init__.py` — `get_ip_address()`, the Flask-Limiter key function
  - `app/utils.py` — `ip_address()` — IP bans, country blocking, and the IP
    recorded on users/posts/instances
- **Test:** `tests/security/test_admin_ip_allowlist.py`,
  `tests/security/test_sp026_ip_address_forgery.py`
- **Upstream status:** PRESENT upstream — `app/utils.py`'s `ip_address()` is
  unchanged from upstream as of v1.7.10
- **Severity:** the admin-API instance was High (defeats an access-control
  gate outright — see SP-025). The app-wide instance was Medium and
  conditional: reachable only if `CF-Connecting-IP` were ever absent, which,
  given this deployment's Cloudflare-only origin, means never in practice —
  but nothing in the code enforced that assumption.
- **Fix summary:** both functions read `request.headers.get("X-Forwarded-For")`
  as a fallback and took the *leftmost* entry — the client's own, unverified
  claim about who they are, prepended before any proxy sees the request.
  `X-Forwarded-For` is append-only, so only the *rightmost* entries are
  trustworthy (added by infrastructure you control). Fixed by dropping the
  raw-header fallback in favor of `request.remote_addr`, which
  `ProxyFix(x_for=1)` already resolves from the rightmost hop. Confirmed
  topology (`client -> Cloudflare -> haproxy -> app`, one hop) makes
  `x_for=1` correct; see `docs/TRUSTED_CLIENT_IP.md`.
- **Note:** `get_ip_address()` is the Flask-Limiter key function for all 13
  `@limiter.limit` endpoints (login, register, password reset, search) — the
  forgeable fallback would have let a client vary the header per request to
  dodge its own rate limit, not just impersonate an allowed source.

### SP-027 — Admin rate limiter failed open on any Redis exception

- **Origin:** pre-existing in this fork; introduced with the private
  registration admin API's monitoring/rate-limiting module
- **Files:**
  - `app/api/admin/monitoring.py` — `check_rate_limit()`'s exception branch;
    `_check_rate_limit_fallback()`'s process-local bucket
- **Test:** `tests/security/test_sp027_ratelimit_fail_open.py`
- **Upstream status:** N/A — fork-only feature, no upstream equivalent
- **Severity:** the rate limiter is one of four gates in front of an
  account-provisioning API (see SP-025); this bug meant any Redis
  disruption — deliberate or incidental — removed the gate entirely rather
  than degrading it.
- **Fix summary:** `check_rate_limit()`'s `except Exception` branch used to
  return `{"allowed": True}` — Redis being unreachable didn't just lose
  accuracy, it switched the limiter off, on endpoints that create, ban, and
  delete accounts. It now degrades to `_check_rate_limit_fallback()`, which
  still enforces a real bound. The fallback itself was also inert: it stored
  counts in `flask.g`, which is per-request under gunicorn, so every fallback
  check saw a fresh empty bucket and always allowed. It now uses a
  module-level dict guarded by a `threading.Lock`.
- **Known limitation:** under multiple gunicorn workers, the fallback bound is
  per-worker, not global — the effective limit while Redis is down is
  `workers × configured`, not `configured`. A real bound, deliberately chosen
  over failing open; Redis remains the accurate, shared enforcement point.

## When upstream finally patches one of these

When upstream ships a fix that closes the vulnerability, audit the upstream patch and our patch side-by-side. If upstream's is equivalent or stricter, switch to upstream's during the merge and update this file to mark the patch as "Upstream-equivalent — superseded in vX.Y.Z". Keep the regression test — it now also verifies upstream's fix.
