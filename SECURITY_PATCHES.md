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
