# Security Audit — 2026-05-15 (Round 3, ActivityPub semantics + CVE comparison)

**Branch:** `20260515/sec-audit-round3` (sits on `20260515/sec-audit-round2`)
**Scope:** Two parallel angles covering surface area Rounds 1-2 didn't touch.
**Auditors:** Two parallel agents — federation/ActivityPub semantics deep-dive, and external CVE comparison against Lemmy + Mastodon recent public disclosures.
**Status:** Embargoed — keep this report private until the disclosure window opens.

---

## TL;DR

Round 3 was intentionally orthogonal to Rounds 1-2. The AP-semantics agent surfaced *design-level* findings (Move authority, Announce inner-object trust, instance silencing semantics, vote inflation) — interesting context but mostly *not* patchable bugs without spec-level discussion. The CVE-comparison agent surfaced *concrete patches* by mapping recent Lemmy/Mastodon disclosures against PieFed's code, yielding **3 actionable fixes (SP-014, SP-015, SP-016)**. Two prior-round patches (SP-002, SP-006/SP-010) also got external confirmation by covering 3 of the Lemmy/Mastodon advisories with zero PieFed-side work.

| ID | Severity | Patched? | Where | Source |
|---|---|---|---|---|
| SP-014 | HIGH | yes | private-community variant 3/4/5/6 gate | mirrors Lemmy GHSA-95q8-x6r6-672m |
| SP-015 | MEDIUM | yes | email-enumeration via flash messages | mirrors Lemmy GHSA-qxrw-f6fh-34r7 |
| SP-016 | MEDIUM | yes | HEAD-request SSRF (head_request + mime_type_using_head) | mirrors Lemmy GHSA-c482-7gjx-pp36 |
| F-AP-1 | HIGH | deferred | Move bidirectional verification | needs Move semantics spec decision |
| F-AP-2 | HIGH | deferred | Announce inner-object trust | needs trace of recursive process_inbox_request |
| F-AP-3 | MEDIUM | deferred | instance silencing semantics | design-ambiguous (limit-like vs suspend-like) |
| F-AP-4 | MEDIUM | deferred | remote vote inflation | mitigation is rate-limiting (skill-excluded class) |
| F-CVE-B2 | MEDIUM | deferred | `private_instance` not enforced in alpha API | broad scope — needs per-endpoint analysis |
| F-CVE-MAST-1 | UNCLEAR | tracked | remote suspension bypass via boost | deeper trace of `resolve_remote_post` needed |

---

## Methodology

Two parallel agents, with non-overlapping angles:

1. **AP semantics audit** — 10 attack classes covering Move spoofing, Announce chains, JSON-LD parser surface, instance silencing, vote inflation, reply spoofing, Delete authorization, Block edge cases, activity-id uniqueness, and community-management activities.
2. **External CVE comparison** — examined ~15 recent Lemmy + Mastodon advisories from GitHub Security Advisories database; for each, traced PieFed's code to determine APPLIES / PARTIALLY APPLIES / DOESN'T APPLY / COVERED status.

The pairing was deliberate: agent 1 reasoned internally about what attacks the protocol allows; agent 2 brought external knowledge of what attacks have actually been disclosed against neighbors. The yield profiles were complementary — agent 1 found design questions, agent 2 found concrete patches.

---

## HIGH — patched (SP-014)

### SP-014 — Private community sidebar leak in `community_view`

- **File:** `app/api/alpha/views.py` (top of `community_view`)
- **Source:** CVE-comparison agent — mirrors Lemmy [GHSA-95q8-x6r6-672m](https://github.com/LemmyNet/lemmy/security/advisories/GHSA-95q8-x6r6-672m) (2026-04-29)
- **Description:** The `/community/*` API endpoints (variants 3, 4, 5, 6) returned the full sidebar (`description`, `posting_warning`, `banner`, `icon`, modlist) for any community — including those flagged `private = True` — without checking membership. `post_view` already enforces this check at line 287; `community_view` did not.
- **Exploit:** Any unauthenticated or non-member user queries `/api/alpha/community?id=<private-community-id>` and reads the sidebar / modlist. Lemmy disclosed and patched the same pattern on 2026-04-29.
- **Fix:** Added the same precondition gate at the top of `community_view` for variants 3/4/5/6: `if community.private and (user_id is None or community.id not in community_membership_private(user_id)): raise Exception('Private community - membership required')`.

---

## MEDIUM — patched (SP-015 + SP-016)

### SP-015 — Email enumeration via differential flash messages

- **Files:** `app/auth/routes.py` — `resend_email`, `reset_password_request`
- **Source:** CVE-comparison agent — mirrors Lemmy [GHSA-qxrw-f6fh-34r7](https://github.com/LemmyNet/lemmy/security/advisories/GHSA-qxrw-f6fh-34r7) (2026-04-30)
- **Description:** Both endpoints flashed distinct messages depending on whether the submitted email was registered. Even with the existing rate limits (`20 per day; 10 per 5 minutes`), trivial to enumerate targeted addresses.
- **Fix:** Both branches now flash the same neutral "If an account exists, a link has been sent" message and redirect to the same path. Server-side handling and logging are unchanged.

### SP-016 — HEAD-request SSRF

- **Files:** `app/activitypub/ssrf_guard.py` (new `safe_httpx_head`), `app/utils.py` (`head_request`, `mime_type_using_head`)
- **Source:** CVE-comparison agent — mirrors Lemmy [GHSA-c482-7gjx-pp36](https://github.com/LemmyNet/lemmy/security/advisories/GHSA-c482-7gjx-pp36) (2026-04-13)
- **Description:** SP-002 wrapped GETs. HEADs went directly to `httpx_client.head` with no IP validation. While HEAD doesn't return a body, an attacker can still learn port-open status, response headers (`Server`, `X-Powered-By`), and probe internal services with attacker-supplied URLs. Reachable via `is_image_url` called on community/feed/post `icon_url` / `banner_url` user inputs.
- **Fix:** Added `safe_httpx_head` to the guard module; routed both call sites through it.

---

## Findings deferred — with rationale

### F-AP-1 / F-AP-5 — Move bidirectional verification

- **File:** `app/activitypub/routes.py:2536-2559`
- **Why deferred:** The Move handler requires the actor to be (a) the post author, (b) a moderator of the origin community, or (c) a same-instance admin of the origin. None of those checks let an outright attacker move arbitrary posts; the attack narrative reduces to "a mod-of-origin can move posts to ANY target community without target's consent" — a moderation-abuse design question, not a federation-bypass vuln. Patching needs a target-side acknowledgment design (`alsoKnownAs`, two-way handshake) that should be discussed at the protocol/spec level, not slipped into an emergency patch. Tracked for follow-up.

### F-AP-2 — Announce inner-object trust

- **File:** `app/activitypub/routes.py:1304-1305`
- **Why deferred:** Need to trace whether the recursive `process_inbox_request` for an Announce-wrapped object actually trusts the inner dict's `actor` claim or re-fetches from authoritative source. The dict-vs-string handling around line 1265 calls `resolve_remote_post` which may or may not re-verify. SP-001's strict-reject covers the unsigned-bypass at the outer envelope; whether the inner object is similarly hardened needs a deeper trace than this round permitted. Tracked for follow-up — this is the highest-priority deferral.

### F-AP-3 — Instance silencing not enforced on inbound activities

- **Files:** `app/activitypub/routes.py shared_inbox`, `app/activitypub/util.py:1809` (the one cosmetic use of `silenced`)
- **Why deferred (design-ambiguous):** `Instance.silenced` is currently used only to gate `community.show_all` in the feed-display path — i.e., it models Mastodon's "limit" semantics (visibility-only) rather than "suspend" semantics (drop inbound). Adding an inbound block would be a semantic CHANGE, not a bug fix. Worth raising as a UX/admin question: is "silenced" supposed to drop activities, or just hide them from feeds? If the former, the patch is one-line; if the latter, no patch is correct. Defer pending a deliberate decision.

### F-AP-4 — No rate-limiting on remote-actor votes

- **File:** `app/activitypub/util.py process_upvote`
- **Why deferred:** A hostile remote instance can spawn N actors and send N votes; PieFed accepts them all. The proper mitigation in fediverse is **admin defederation** (already supported), not per-vote rate limits — which is also a security-review hard-exclusion class. Adding per-instance vote weighting is a feature request, not a vulnerability fix.

### F-CVE-B2 — `private_instance` not enforced in alpha API

- **Files:** all alpha-API handlers in `app/api/alpha/routes.py` (versus `app/utils.py:1930` `login_required_if_private_instance` web decorator)
- **Source:** CVE-comparison agent — mirrors Lemmy GHSA-jmxc-hhwx-gvv3
- **Why deferred:** Real gap, broad scope. The web routes have the `login_required_if_private_instance` decorator; the alpha-API routes don't. Patching needs a per-endpoint analysis: which API endpoints should still respond to unauthenticated callers on a private instance (e.g., webfinger, nodeinfo, actor profile for federation discovery) versus which should be gated (post/list, community/list, user). Tracked as the next-most-important follow-up after F-AP-2.

### F-CVE-MAST-1 — Remote suspension bypass via boost (Mastodon GHSA-5h2f-wg8j-xqwp)

- **Files:** Announce-by-URL path at `app/activitypub/routes.py:1252-1267` calls `resolve_remote_post` without an explicit ban check on the post's author.
- **Status:** UNCLEAR per the CVE-comparison agent (confidence 4). Worth a focused trace of `resolve_remote_post`'s ban-handling behavior in a follow-up. Not patched in this round because the actual ban-check semantics need verification before adding a check that might suppress legitimate content.

---

## Confirmed coverage — no PieFed-side work needed

The CVE-comparison agent confirmed that prior patches already cover these recent disclosures:

- **Lemmy GHSA-h6hf-9846-xwrq** — SSRF via og:image. **Covered by SP-006 + SP-010.**
- **Lemmy GHSA-q537-8fr5-cw35** — `0.0.0.0` SSRF bypass. **Covered by SP-002** (`is_unspecified` check).
- **Mastodon GHSA-xfrj-c749-jxxq** — SSRF protection bypass via IPv4-mapped IPv6 / alt encodings. **Covered by SP-002** (the Python `ipaddress` properties catch these on 3.13+).

Several other recent advisories don't apply for architectural reasons (PieFed lacks Webmention, lacks AUTHORIZED_FETCH, lacks quote authorization, lacks pict-rs proxy URLs, has different file-deletion authz).

---

## Verification

```
SERVER_NAME=localhost uv run pytest tests/security/ -q
```

98 passed at audit time (88 from rounds 1-2 + 10 new from round 3).
