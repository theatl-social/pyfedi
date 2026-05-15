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

### SP-013 — Email verification token cleared after first use

- **Disclosure:** 2026-05 (round-2 audit, concurrency / token-replay)
- **Files:**
  - `app/auth/routes.py` — `verify_email()`
- **Test:** `tests/security/test_sp013_verification_token_cleared.py`
- **Upstream status:** NOT FIXED upstream
- **Fix summary:** `verify_email` set `user.verified = True` but never cleared `user.verification_token`. A captured token (email-server log, ESP cache, browser history, referrer-header leak) could be replayed against the same account. The `if user.verified` guard only catches re-execution within the *same* request; an attacker could race against a not-yet-verified account or replay later. Now `user.verification_token = None` is set immediately before the commit.

### SP-004 — Shell-call command injection in CLI translate command

- **Disclosure:** 2026-05 (private, embargoed) — lower severity since it requires CLI access, but still real
- **Files:**
  - `app/cli.py` — `translate init/update/compile` use `subprocess.run([...])` with list args; `init` validates `lang` against an ISO-code allowlist regex
  - `app/activitypub/util.py` — `public_key()` openssl key generation also moved to `subprocess.run`
- **Test:** `tests/security/test_cli_lang_arg_safe.py`
- **Upstream status:** NOT FIXED upstream as of v1.6.24
- **Fix summary:** The `translate init` command concatenated the `lang` CLI argument into a string passed to the legacy POSIX shell-call helper. An attacker with CLI access (or a misconfigured automation system) could inject arbitrary shell. Now the call uses `subprocess.run([...])` with list args (no shell) and validates `lang` against `^[a-z]{2,3}(_[A-Z]{2})?$` first.

## When upstream finally patches one of these

When upstream ships a fix that closes the vulnerability, audit the upstream patch and our patch side-by-side. If upstream's is equivalent or stricter, switch to upstream's during the merge and update this file to mark the patch as "Upstream-equivalent — superseded in vX.Y.Z". Keep the regression test — it now also verifies upstream's fix.
