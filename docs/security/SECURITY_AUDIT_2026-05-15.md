# Security Audit — 2026-05-15

**Branch:** `20260515/sec-audit-findings` (sits on `20260515/sec-patches-disclosed` and `20260515/merge-upstream-v1624`)
**Scope:** Whole-codebase audit following the four-vuln embargoed disclosure (SP-001..SP-004) and the v1.6.24 upstream merge.
**Auditors:** Multiple parallel agents — `security-review` skill (branch diff), `pr-review-toolkit:silent-failure-hunter` (new patches), `pr-review-toolkit:type-design-analyzer` (new types), and a manual whole-codebase Explore agent.
**Status:** Embargoed — keep this report private until disclosure window opens.

---

## TL;DR

The four originally-disclosed vulnerabilities (SP-001..SP-004) are correctly patched. The whole-codebase audit identified **four additional issues** (SP-005..SP-008) — three CRITICAL and one HIGH — all of which we patched in the same Phase-3 commit. Plus three MEDIUM/LOW type-design improvements to the SSRF guard for better telemetry, tracked as follow-ups.

---

## Methodology

1. **`security-review` skill** ran on the full branch diff vs `main`. Result: 0 high-confidence vulns introduced by the diff itself.
2. **`silent-failure-hunter`** focused on the new patches' exception-handling flow. Result: clean. No silent drops introduced; one pre-existing precheck-failure issue surfaced (became SP-008).
3. **`type-design-analyzer`** reviewed `SsrfBlocked`, `validate_outbound_url` return shape, and `_validate_secret_key`. Result: design-quality improvements, no exploitable issues.
4. **Manual whole-codebase Explore agent** swept eight audit areas: SSRF coverage gaps, auth/JWT, templates safe-filter usage, SQL text-interpolation, file handling, crypto/randomness, subprocess sweep, dangerous primitives, plus an open-redirect sweep that surfaced from following the redirect-handling code.

Each finding was independently filtered for confidence ≥ 8 per the security-review skill's false-positive criteria.

---

## Findings

### CRITICAL — patched in Phase 3

#### SP-005 — Predictable token / ID generation

- **File:** `app/auth/util.py:50-58` (`random_token`); `app/utils.py:328-329` (`gibberish`)
- **Description:** Both functions used Python's `random` module with `.choice()` (Mersenne Twister, predictable from observed output). With ~624 observed outputs the internal state can be reconstructed. `random_token(16)` is used for password-reset / email-verification tokens.
- **Exploit:** Self-serve enough password-reset flows for accounts you control, observe the tokens, reconstruct the PRNG state, predict the next reset token for any victim account → account takeover.
- **Fix:** Switched both to `secrets.choice`. See SECURITY_PATCHES.md SP-005.

#### SP-006 — SSRF in `retrieve_metadata_of_url`

- **File:** `app/community/routes.py:2634-2638`
- **Description:** Function called `httpx_client.get(url, follow_redirects=True)` directly with the user-supplied URL when generating the OpenGraph preview for a link post. Bypassed the SP-002 SSRF guard.
- **Exploit:** Create a link post pointing at an internal address, e.g. `http://127.0.0.1:6379/`; the response surfaces in the post title/description preview.
- **Fix:** Routed through `safe_httpx_get`. See SECURITY_PATCHES.md SP-006.

#### SP-007 — Open redirect via `instance_url` form field

- **File:** `app/user/routes.py:1814-1828` (`fediverse_redirect`)
- **Description:** `form.instance_url.data` was interpolated into a redirect URL with no validation. Inputs like `evil.com/path/to/phish` or `evil.com@victim.com/...` redirected victims off-site.
- **Exploit:** Send victim a link to `https://piefed.example/u/alice/from/...` with `instance_url=evil.com/login-phish`; the platform 302s them to the attacker's site under a URL that looks like the legitimate platform.
- **Fix:** Added `_SAFE_INSTANCE_HOST_RE` (LDH-label hostname regex; no scheme/path/userinfo/port). See SECURITY_PATCHES.md SP-007.

### HIGH — patched in Phase 3

#### SP-008 — Precheck failure silently continued in `shared_inbox`

- **File:** `app/activitypub/routes.py:883-888`
- **Description:** `HttpSignature.precheck` enforces digest-and-date freshness. When it raised `VerificationFormatError`, the code logged and continued. The downstream `verify_request` call only re-checks the digest if the sender included it in signed-headers, and doesn't independently re-verify date freshness, so a malformed digest could slip past.
- **Note:** Pre-existing — surfaced by the silent-failure-hunter agent during the SP-001 review. Not introduced by SP-001's strict-reject change but adjacent to it.
- **Fix:** Added `return "", 400` after the precheck-failure log call.

### MEDIUM — tracked as follow-ups (not patched in this branch)

#### M-1: SSRF coverage gaps in callers that bypass `get_request()`

- **Files:**
  - `app/shared/tasks/users.py:37, 86` — federation API calls (`is_ip_banned`) via `httpx_client.post` to federation-controlled domain. Domain comes from our DB, not direct user input — lower risk than the SP-006 case but inconsistent with SP-002's coverage.
  - `app/shared/tasks/maintenance.py:969` — hardcoded fediverse.observer URL. No SSRF risk but inconsistent.
  - `app/translation.py:60, 78, 95` — config-sourced `TRANSLATE_ENDPOINT`. No SSRF risk under any reasonable threat model.
  - `app/models.py:493` — hardcoded Cloudflare API. Safe.
- **Status:** Not exploitable in the current threat model (federation-controlled or hardcoded URLs), but should be routed through `get_request()` for uniformity. Defense-in-depth follow-up.

#### M-2: `SsrfBlocked` carries opaque string messages

- **File:** `app/activitypub/ssrf_guard.py`
- **Source:** `type-design-analyzer`
- **Description:** Six rejection categories (scheme, no-host, metadata-literal, DNS failure, non-public-IP, redirect-cap) collapse to a free-form message. Telemetry has to regex.
- **Suggested fix:** Add `SsrfReason` enum, make `SsrfBlocked` a frozen dataclass.

#### M-3: `validate_outbound_url` returns positional `tuple[str, list[str]]`

- **File:** `app/activitypub/ssrf_guard.py`
- **Source:** `type-design-analyzer`
- **Suggested fix:** NamedTuple `ValidatedTarget(host: str, resolved_ips: tuple[str, ...])`, or split into two functions.

### LOW — tracked as follow-ups

#### L-1: Three independent boolean kwargs on SSRF entry points

- **File:** `app/activitypub/ssrf_guard.py`
- **Suggested fix:** `SsrfPolicy` enum (`STRICT`, `DEV_LOOPBACK`, `ADMIN_PROBE`).

#### L-2: `_validate_secret_key` lives outside `Config`

- **File:** `app/__init__.py`
- **Suggested fix:** Move to `Config.validate()` or a `SecretKey` newtype.

#### L-3: Captcha character generator uses `random.choice`

- **File:** `app/utils.py:3677` (captcha digit selection)
- **Description:** Lower stakes than SP-005 — captchas aren't auth tokens — but inconsistent with the SP-005 sweep. The captcha UUID is correctly generated via `os.urandom(12).hex()`.
- **Suggested fix:** Switch to `secrets.choice` for uniformity.

#### L-4: `redirect()` from `request.args.get('redirect')` without validation

- **File:** `app/user/routes.py:955`
- **Description:** A `?redirect=` query parameter is passed to Flask's `redirect()` without checking it's same-origin.
- **Status:** Re-verify scope; if reachable from an unauthenticated request it's HIGH and should be patched.

#### L-5: HX-Redirect derived from `HX-Current-Url` request header

- **File:** `app/post/routes.py:1388, 1418, 1443, 1465, 1548, 1622, 1762, 1790, 1801`
- **Description:** Server reads `HX-Current-Url` from request and writes it back as `HX-Redirect`. The header is client-controlled, so the client can already direct itself anywhere — but if the response is observable to a third party (not in the typical HTMX flow), it's a redirect amplifier.
- **Status:** Out-of-scope for this audit pending threat-model clarification.

### INFO — verified safe

- All JWT encode/decode call sites use `current_app.config['SECRET_KEY']` correctly (and SP-003 ensures that key is strong).
- All file uploads use randomized filenames + extension allowlist; no path traversal.
- All Jinja safe-filter usage on user content (about_html, body_html, sidebar_html, cms_page.body_html) operates on values pre-sanitized by `allowlist_html()` in the markdown→html pipeline.
- All SQL text-interpolation use `current_app.config['SERVER_NAME']` (config-sourced, not user input). Parameterized values use `:placeholder`.
- No use of dynamic-code-evaluation primitives, unsafe deserialization, unsafe yaml load, or dynamic imports.
- All shell-helper invocations cleared by SP-004; only `subprocess.run([...])` with list args remains.

---

## Out-of-scope follow-ups (post-embargo)

- File coordinated patches against upstream `rimu/pyfedi` for SP-001..SP-008
- Replace the legacy openssl shell-out in `app/activitypub/util.py public_key()` with the `cryptography` library (already noted in `SECURITY_PATCHES.md`)
- Audit other prior fork features that may have silently regressed during past upstream merges (similar to the SP-001..SP-004 silent regression pattern)
- Close the DNS-rebinding TOCTOU residual risk on the SSRF guard (custom httpx transport that pre-resolves and dials by IP while preserving SNI)
- Re-verify L-4 (redirect query param) under the actual auth flow; patch if reachable unauthenticated
- Patch L-3 (captcha randomness) for uniformity with SP-005

---

## Verification of patches

```
SERVER_NAME=localhost uv run pytest tests/security/ -q
```

71 passed at audit time (across SP-001..SP-008 plus SsrfBlocked unit tests).
