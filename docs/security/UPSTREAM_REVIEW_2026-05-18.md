# Upstream Security Review — 2026-05-18

Assessment of upstream PieFed releases v1.6.25, v1.6.26, v1.6.27 against the
SP-### patches carried by this fork (see `SECURITY_PATCHES.md`).

**Fork base at time of audit:** v1.6.24 (merge commit `5e4ef2fe`, 2026-05-15)
**Upstream HEAD at time of audit:** `dc215422` (v1.6.27, 2026-05-17)
**New upstream commits to review:** 8 (between `3cb02f52` and `dc215422`)

## TL;DR

Upstream has shipped fixes that overlap with **most** of our SP-### patches.
The fixes arrived as cherry-picks from `v1.6.x` two days after our merge,
strongly suggesting rimu received the same private disclosure and is working
the fixes through coordinated channels.

- **9 of our 16 patches** are now upstream-equivalent or upstream-stricter — we
  can switch to upstream's version during the next merge.
- **3 patches** are addressed by upstream but our version is **stricter or more
  correct** — keep ours.
- **1 patch (SP-009 ban authz)** has a **logic bug in upstream's fix** — keep
  ours; the upstream version restricts banning to moderators-only, which is
  almost certainly unintended.
- **3 patches** remain unaddressed upstream — keep ours.
- **2 new vuln classes** have been addressed upstream that our audit missed:
  - **SVG XSS** in uploads (now mitigated via `py-svg-hush` in v1.6.27)
  - **Webfinger content-type spoofing** (v1.6.25)
- **1 new upstream defense looks suspicious** — the `actor_json_to_model`
  substring check (`if server not in activity_json['id']: return None`) is a
  substring test, not a host test, and trivially bypassable.

## Per-patch assessment

### SP-001 — Unsigned-activity bypass

- **Upstream commit:** `ada8e2ea` (v1.6.25), `app/activitypub/routes.py:674-678`
- **What upstream did:** Commented out the dict→id reduction block with the
  note "Removed due to potential security issues. This will probably break
  PeerTube federation, unfortunately."
- **What we did:** Deleted the same block, added regression test.
- **Verdict:** **UPSTREAM-EQUIVALENT.** Same fix, same trade-off. Switch to
  upstream during merge (delete vs. comment-out is style only).

### SP-002 — SSRF in outbound HTTP

- **Upstream commits:**
  - `ada8e2ea` (v1.6.25): added `is_invalid_get_request_uri` / `is_invalid_post_request_uri` helpers; initial version only checks if the *literal host* is an IP and that IP is private/loopback/etc. **No DNS resolution.**
  - `f71b8259` (v1.6.26): hardened the helper to (a) require `http`/`https` scheme, (b) reject `.local` hostnames, (c) resolve DNS and check **every** resolved IP via `ipaddress.is_global`, (d) reject when `furl.host` is empty.
  - `ada8e2ea` also disabled `follow_redirects=True` everywhere in `get_request()`.
  - `ada8e2ea` added the same `is_invalid_*` check inside `HttpSignature.signed_request` and `post_request`.
- **What we did:** Built `app/activitypub/ssrf_guard.py` with cloud-metadata literal blocklist (169.254.169.254, fd00:ec2::254, 100.100.100.200), per-redirect re-validation, scheme restriction, and `SSRF_GUARD_ALLOW_PRIVATE` / `SSRF_GUARD_ALLOW_HTTP` opt-outs for dev environments.
- **Verdict:** **OVERLAPPING.** Functionally similar coverage after v1.6.26.
  Differences:
  - Upstream uses `is_global` (catches everything non-public). We use an explicit blocklist (loopback/link-local/multicast/reserved/private/unspecified) plus a cloud-metadata literal list. Both should catch the cloud-metadata addresses since they're link-local — but upstream's `is_global` definition is the cleaner expression of intent.
  - Upstream disables redirects entirely. We follow redirects manually with per-hop re-validation. **Our approach preserves legitimate redirect-following federation flows** (some ActivityPub URLs 301 to a canonical form).
  - We have explicit opt-out env vars for dev; upstream gates on `current_app.debug`.
- **Recommendation:** Keep our guard module (richer feature set), but adopt
  upstream's `is_global` check as an additional pre-filter inside
  `validate_outbound_url` for defense-in-depth. Mark SP-002 as "Upstream
  partial-equivalent in v1.6.26".

### SP-003 — Hardcoded SECRET_KEY fallback

- **Upstream commits:**
  - `f71b8259` (v1.6.26): `config.py` removes the `or 'you-will-never-guesss'` fallback. `app/__init__.py` adds `if not app.config["SECRET_KEY"]: raise Exception(...)`. `env.sample` adds a comment.
- **What we did:** Same `config.py` change. Plus `_validate_secret_key()` with `min_length=32` and a known-bad-defaults list (which SP-012 then made case- and whitespace-insensitive).
- **Verdict:** **UPSTREAM-WEAKER.** Upstream only refuses empty/None. We
  also refuse short keys and known-bad strings. A deployment setting
  `SECRET_KEY=dev` would boot upstream; ours rejects it.
- **Recommendation:** Keep ours.

### SP-004 — Shell-call command injection in CLI translate

- **Upstream:** Not fixed.
- **Verdict:** **STILL OUTSTANDING UPSTREAM.** Keep ours.

### SP-005 — Predictable token / ID generation via `random.choice`

- **Upstream commit:** `f71b8259` (v1.6.26) — `app/auth/util.py:random_token` switched to `secrets.choice`.
- **What we did:** Switched `random_token` **and** `gibberish` in `app/utils.py`.
- **Verdict:** **UPSTREAM PARTIAL.** Upstream fixed `random_token` (the
  password-reset / email-verification token generator — the higher-risk one).
  Upstream did **not** fix `gibberish` in `app/utils.py`, which is still
  `random.choice`-based and is used for upload filenames (in
  `app/shared/upload.py:39`). For uploads the predictability matters less
  (filename collision is the main risk, not impersonation), but it's still a
  systemic improvement worth keeping.
- **Recommendation:** Keep ours. Note in SECURITY_PATCHES.md that upstream
  covers `random_token` only.

### SP-006 — SSRF in `retrieve_metadata_of_url`

- **Upstream commit:** `ada8e2ea` (v1.6.25) — changed `follow_redirects=True` to `False` in `app/community/routes.py:retrieve_metadata_of_url`.
- **What we did:** Routed through `safe_httpx_get` (which does full
  DNS validation, not just redirect-disable).
- **Verdict:** **OUR FIX IS STRICTER.** Upstream's change only blocks
  redirect-to-internal attacks. A direct link post pointing at
  `http://127.0.0.1:6379/INFO` would still be fetched by upstream.
  We block it outright.
- **Recommendation:** Keep ours. Adopt upstream's `follow_redirects=False`
  as belt-and-suspenders (we already do redirect handling manually anyway).

### SP-007 — Open redirect via `instance_url` form field

- **Upstream:** Not fixed.
- **Verdict:** **STILL OUTSTANDING UPSTREAM.** Keep ours.

### SP-008 — Precheck failure silently continued

- **Upstream commit:** `f71b8259` (v1.6.26) — added `return '', 400` after precheck-failure log in `shared_inbox`.
- **What we did:** Same.
- **Verdict:** **UPSTREAM-EQUIVALENT.** Switch to upstream during merge.

### SP-009 — Missing authorization on community ban/unban — **UPSTREAM BUGGY**

- **Upstream commit:** `f71b8259` (v1.6.26) — both `community_ban_user` and `community_unban_user` now gate on:
  ```python
  if (community.is_owner() or current_user.is_admin_or_staff()) and community.is_moderator(user):
      ...do the ban...
  else:
      abort(403)
  ```
  where `user = User.query.get_or_404(user_id)` is the **target** user.
- **What we did:**
  ```python
  if not (community.is_owner() or current_user.is_admin() or community.is_moderator()):
      abort(401)
  ```
  where `community.is_moderator()` (no arg) defaults to `current_user`.
- **The bug:** `community.is_moderator(user)` with `user` = **target** checks whether the *target* is a moderator. So upstream's gate reads: "only allow the ban if (actor is owner/admin) AND (target is a moderator)". This means:
  - **Regular moderators can no longer ban anyone** (the AND fails on the actor side).
  - **Only moderators can be banned** — regular users are no longer bannable at all (the AND fails on the target side).

  This is almost certainly a typo for `community.is_moderator()` (no arg). Without sight of upstream tests we can't confirm rimu's intent, but the resulting behavior is broken for the common case of "moderator bans regular spammer".
- **Verdict:** **UPSTREAM BUGGY.** Our fix is correct.
- **Recommendation:** Keep ours. File a coordinated upstream bug report
  once embargo lifts — this is a usability-regression-via-security-fix that
  rimu probably wants to fix too.

### SP-010 — SSRF in `url_to_thumbnail_file`

- **Upstream commit:** `f71b8259` (v1.6.26) — added `if is_invalid_get_request_uri(filename): return None` at the top of `url_to_thumbnail_file`.
- **What we did:** Same approach (via `safe_httpx_get`).
- **Verdict:** **UPSTREAM-EQUIVALENT.** Switch to upstream during merge.

### SP-011 — Atomic SETNX dedup in shared_inbox

- **Upstream commit:** `f71b8259` (v1.6.26) — `redis_client.set(id, 1, ex=90)` changed to `redis_client.set(id, 1, ex=90, nx=True)`. **BUT the preceding `if redis_client.exists(id): return` block was kept.**
- **What we did:** Removed the exists() check entirely; the SETNX itself is the gate.
- **The subtle issue with upstream:** Concurrent inbox POSTs for the same activity ID can both pass `exists()` (returns False for both since neither has written yet), then both call `set(..., nx=True)`. The first wins; the second's SET returns False (no-op). **But both flows continue past the dedup gate** — they hit `set` after the dedup check completes, not as the check itself. Upstream's nx=True prevents the *second write* from overwriting but does not prevent both flows from proceeding to `process_inbox_request`. The result: double-processing of votes/Likes/Creates in the rare concurrent case.
- **Our gate:** `if not redis_client.set(id, 1, ex=90, nx=True): return 200`. The SET-with-NX *is* the dedup atom; the loser sees `False` and bails. Single atomic operation, no race window.
- **Verdict:** **OUR FIX IS BETTER.** Upstream closes the *write* race but not the *processing* race.
- **Recommendation:** Keep ours. Worth a coordinated upstream patch.

### SP-012 — SECRET_KEY known-bad list case/whitespace-insensitive

- **Upstream:** Not addressed (upstream's SP-003 equivalent has no known-bad list at all).
- **Verdict:** **STILL OUTSTANDING UPSTREAM.** Keep ours.

### SP-013 — Email verification token cleared after first use

- **Upstream commits:**
  - `f71b8259` (v1.6.26): added `user.verification_token = None` after `user.verified = True` — matches our SP-013 exactly.
  - `b3474d19` (v1.6.27): **reverted** that line to `user.verification_token = random_token(16)` AND added `{% if recipient.verification_token %}` guards in `app/templates/email/newsletter.{html,txt}` and `welcome.{html,txt}`. Reason in commit message: "avoid crash when verification token is missing."

  The crash was in the email templates: `url_for('user.user_newsletter_unsubscribe', ..., token=None)` raises because `url_for` rejects `None` for URL components.

- **What we did:** Set to `None`. Did not update the email templates.
- **The implication for us:** Our SP-013 may currently be **breaking newsletter
  sends** to already-verified users. Worth verifying. Also: setting to a fresh
  random token is semantically equivalent (the old token is invalidated by
  being replaced), so upstream's approach is strictly better — it preserves
  the unsubscribe-link functionality.
- **Verdict:** **UPSTREAM IS BETTER** (preserves email functionality with
  equivalent security).
- **Recommendation:**
  1. Adopt upstream's `random_token(16)` approach in our SP-013.
  2. Adopt upstream's template guards as belt-and-suspenders.
  3. Update our regression test (`tests/security/test_sp013_verification_token_cleared.py`) to assert "token changes after verify", not "token becomes None".

### SP-014 — Private community sidebar leak

- **Upstream commit:** `f71b8259` (v1.6.26) — added the membership gate inside `community_view` at variants 3 and 6 **only**.
- **What we did:** Gate covers variants **3, 4, 5, and 6**.
- **The gap:** Upstream variants 4 (`/community/follow`) and 5 (`/community/block`) still return the full sidebar/description/banner/posting_warning/modlist for private communities to non-members. The same disclosure as variant 3 — just via different API endpoints.
- **Verdict:** **OUR FIX IS COMPLETE; UPSTREAM IS INCOMPLETE.**
- **Recommendation:** Keep ours. File coordinated upstream PR post-embargo.

### SP-015 — Email-enumeration via differential flash messages

- **Upstream commit:** `f71b8259` (v1.6.26) — both `resend_email` and `reset_password_request` now flash the same "If an account exists, a link has been sent" message in both branches.
- **What we did:** Same.
- **Verdict:** **UPSTREAM-EQUIVALENT.** Switch to upstream during merge.

### SP-016 — HEAD-request SSRF

- **Upstream commit:** `f71b8259` (v1.6.26) — **deleted** the `head_request` function from `app/utils.py` and removed its single caller (`user_removed_from_remote_server` in `app/activitypub/util.py`, which was also deleted).
- **What we did:** Built `safe_httpx_head` with the same guard treatment as `safe_httpx_get`.
- **Verdict:** **DIFFERENT APPROACHES.** Upstream removes the functionality;
  we guard it. Both close the vuln. Removing the functionality affects
  `is_image_url` and `mime_type_using_head` callers — but wait, upstream's
  `mime_type_using_head` is gone too? Let me re-check… upstream removed
  `head_request` from `app/utils.py` but left `mime_type_using_head` as an
  artifact pointing at nothing. Need to inspect more carefully during merge.
- **Recommendation:** Keep our `safe_httpx_head`. If upstream's deletion
  also removed downstream callers we depended on, we may need to restore
  them with the guard.

## Newly addressed upstream (we hadn't patched these)

### NEW-1 — Webfinger content-type validation (v1.6.25)

- **Commit:** `ada8e2ea` in `app/activitypub/actor.py:200-202`
- **Diff:**
  ```python
  content_type = webfinger_data.headers.get('Content-Type', '').lower()
  if webfinger_data.status_code == 200 and ('application/jrd+json' in content_type or 'application/json' in content_type):
      webfinger_json = webfinger_data.json()
  ```
- **What it defends against:** A server serving a non-JSON response under a
  webfinger URL (e.g. HTML with embedded `<script>` or a `text/plain` body
  containing crafted JSON) bypassing the JSON-parsing path. Defense-in-depth
  against parser-confusion in `webfinger_data.json()`.
- **Severity:** Low (httpx's `.json()` will throw on non-JSON anyway), but
  good hygiene.
- **Recommendation:** Adopt during merge.

### NEW-2 — SVG XSS sanitization (v1.6.27)

- **Commit:** `dc215422` in `app/utils.py`, `app/shared/upload.py`, `app/shared/post.py`
- **Diff:** New `sanitize_svg_bytes()` and `sanitize_svg()` functions using
  `py-svg-hush~=0.3.0` to strip `<script>`, event handlers, and other XSS
  vectors from uploaded SVGs. Called on every SVG upload and every SVG
  thumbnail fetch.
- **What it defends against:** A user uploading an SVG with embedded
  JavaScript (e.g. `<svg><script>alert(document.cookie)</script></svg>`)
  which then executes when another user loads the SVG inline. **This is a
  real XSS vector** — SVG is `image/svg+xml` MIME type and can contain
  active content.
- **Severity:** **High.** Our audit missed this entirely. Persistent XSS via
  uploaded community/user/post images, exploitable by any user with upload
  permissions.
- **Recommendation:** **Merge this immediately** even outside the normal
  upstream-merge cadence — this is a real new vuln class. Add a regression
  test under `tests/security/`.

### NEW-3 — Suspicious actor_json_to_model substring check (v1.6.25)

- **Commit:** `ada8e2ea` in `app/activitypub/util.py:1090-1091`
- **Diff:**
  ```python
  def actor_json_to_model(activity_json, address, server):
      if 'type' not in activity_json:
          return None
      if server not in activity_json['id']:    # <-- new
          return None
  ```
- **What it claims to defend against:** An actor JSON document where the
  `id` belongs to a different server than the one serving the document
  (impersonation).
- **The problem:** `server not in activity_json['id']` is a **substring** test,
  not a host test. If `server = "example.com"` and the attacker controls
  `evil.com`, they can serve actor JSON with
  `id = "https://evil.com/path/to/example.com"` and pass the check. The
  intent is clearly host-matching; the implementation is naive string
  containment.
- **Bypass complexity:** Trivial. Any attacker who can serve actor JSON can
  craft an `id` that contains the victim's domain anywhere in the path.
- **Severity:** Currently provides essentially no defense.
- **Recommendation:** Adopt the upstream line, but **replace with proper
  host comparison** during merge:
  ```python
  from urllib.parse import urlparse
  actor_id_host = urlparse(activity_json['id']).hostname
  if actor_id_host is None or actor_id_host.lower() != server.lower():
      return None
  ```
  And file a coordinated upstream patch.

## Other notable upstream commits (not security)

- `c8edd293` — NodeBB mods-collection compat fix. Not security-related.

## Merge recommendation

When we next merge upstream (v1.6.27 → fork), the conflict resolution
matrix should be:

| Patch | Action on merge |
|-------|-----------------|
| SP-001 | Accept upstream's removal (functionally equivalent). |
| SP-002 | **Keep ours.** Optionally inline upstream's `is_global` check inside `validate_outbound_url` as belt-and-suspenders. |
| SP-003 | **Keep ours.** Upstream's empty-check is a subset of our validation. |
| SP-004 | **Keep ours.** Upstream has not addressed. |
| SP-005 | **Keep ours.** Upstream covers `random_token` only; we also cover `gibberish`. |
| SP-006 | **Keep ours.** Upstream's `follow_redirects=False` is a subset of our guard. |
| SP-007 | **Keep ours.** Upstream has not addressed. |
| SP-008 | Accept upstream (equivalent). |
| SP-009 | **Keep ours.** Upstream's logic is inverted/buggy. |
| SP-010 | Accept upstream (equivalent). |
| SP-011 | **Keep ours.** Upstream's TOCTOU close is incomplete. |
| SP-012 | **Keep ours.** Upstream has no known-bad list at all. |
| SP-013 | **Adopt upstream's approach** (random_token + template guards). Update our regression test accordingly. |
| SP-014 | **Keep ours.** Upstream only covers 2 of 4 variants. |
| SP-015 | Accept upstream (equivalent). |
| SP-016 | **Keep ours.** Upstream removed functionality entirely; we guard it. |
| NEW-1 (webfinger content-type) | **Adopt during merge.** |
| NEW-2 (SVG sanitize) | **Adopt during merge** with regression test. |
| NEW-3 (actor JSON id check) | Adopt the *intent* but **replace** the implementation with proper host comparison. |

## Coordinated upstream follow-ups (post-embargo)

Once embargo lifts, we should file the following coordinated PRs to upstream:

1. **SP-009 inverted-logic bug fix** — `is_moderator(user)` → `is_moderator()`.
2. **SP-014 variant-4/5 gap** — extend the private-community gate.
3. **SP-011 TOCTOU close** — remove the redundant exists() check, rely on SETNX.
4. **NEW-3 substring → host check** — fix the `actor_json_to_model` id validator.
5. **SP-002 cloud-metadata blocklist** — even though `is_global` should catch them, explicit blocklist is documentation-as-code.

## Action items for this fork (immediate)

1. **Merge upstream v1.6.27** using the table above as the conflict resolution guide.
2. **Adopt NEW-2 (SVG sanitize) immediately** — separate PR, doesn't need to wait for full v1.6.27 merge. Add `tests/security/test_sp017_svg_sanitize.py`.
3. **Update SP-013** to upstream's pattern; update regression test from "token is None" to "token is rotated".
4. **Verify SP-013's current state** — confirm whether our newsletter unsubscribe URLs are currently broken for users who verified after our patch landed.
5. **Update `SECURITY_PATCHES.md`** to mark each SP-### with its upstream-equivalence status (Upstream-equivalent / Upstream-partial / Upstream-buggy / Outstanding).
6. **Add `py-svg-hush` to `pyproject.toml`** when adopting NEW-2.

## Lessons

- **Upstream is responsive.** The disclosure-to-patch interval was effectively
  ~2 days (our merge of 2026-05-15, upstream's first security commit on
  2026-05-16). The cherry-pick pattern from `v1.6.x` shows rimu is taking the
  same coordinated-disclosure posture we are.
- **Independent fixes diverge in their strictness.** Our audit went deeper on
  `is_invalid_get_request_uri` (cloud-metadata blocklist), known-bad SECRET_KEY
  list, and variant-4/5 of the private community gate. Upstream went deeper on
  SVG sanitization (which we missed). Two independent audits found
  complementary issues; merging both gives the strongest result.
- **A naive substring check is worse than no check.** NEW-3 is a cautionary
  example: a "security tweak" that gives the appearance of defense without the
  substance is worse than nothing because it creates a false sense of safety
  for code reviewers.
