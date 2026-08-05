# Trusted client IP

Where the client IP comes from, which sources are trustworthy, and why it
matters. Written after an audit on 2026-08-05 found the same forgeable-header
pattern in three places.

---

## The rule

**A header is only trustworthy if something you control overwrote it.**

Everything a client sends is attacker-controlled, including headers that
*describe* the client. `X-Forwarded-For` is append-only: each proxy adds the peer
it saw. So the **rightmost** entries are added by your infrastructure and the
**leftmost** entry is whatever the original client typed. Reading the leftmost
entry means trusting the attacker's own claim about who they are.

## What is trustworthy here

| source | trustworthy? | why |
|---|---|---|
| `request.remote_addr` | **yes** | `ProxyFix(x_for=1)` (`app/__init__.py`) resolves this from the rightmost `X-Forwarded-For` hop — the one our own proxy appended |
| `CF-Connecting-IP` | **yes, for traffic through Cloudflare** | Cloudflare overwrites it on every proxied request; a client cannot preserve their own value through CF |
| `X-Forwarded-For` (leftmost) | **no** | fully client-supplied |
| `X-Forwarded-For` (rightmost) | yes, but use `remote_addr` instead — ProxyFix already does this correctly |

**This deployment's origin is reachable only through Cloudflare.** That is what
makes `CF-Connecting-IP` dependable here, and it is a property of the network,
not of the code. If the origin ever becomes directly reachable, the analysis
below changes immediately — so treat "origin is CF-only" as a security control
worth preserving and testing, not an incidental deployment detail.

---

## Current state of the code

### Fixed: the admin API

`app/api/admin/security.py` (`validate_private_registration_request`) used to
read the raw header and take the leftmost entry, so anyone could send
`X-Forwarded-For: <an allowed ip>` and satisfy the IP allowlist. It now uses
`request.remote_addr`.

This was latent while the allowlist itself was inert — it read a `settings` row
nothing ever wrote, so `is_ip_whitelisted()` returned `True` for every address.
Both were fixed together, which matters: fixing only the allowlist would have
produced a control that *looked* like it restricted access while admitting
everyone. Guarded by `tests/security/test_admin_ip_allowlist.py`.

### Known and accepted: `get_ip_address()` / `ip_address()`

`app/__init__.py:45` and `app/utils.py:2138` are identical:

```python
ip = (request.headers.get("CF-Connecting-IP")
      or request.headers.get("X-Forwarded-For")
      or request.remote_addr)
ip = ip[: ip.index(",")].strip()   # leftmost
```

What they feed:

| consumer | if the value were forgeable |
|---|---|
| `get_ip_address()` — the **Flask-Limiter key function** | all 13 `@limiter.limit` endpoints (login, register, password reset, search) get unlimited quota by varying the header per request |
| `user_ip_banned()` → `ban:{ip}` | IP bans bypassable |
| `get_country()` | country blocking bypassable |
| `current_user.ip_address`, post IPs | forged moderation data |

**Why this is currently accepted:** `CF-Connecting-IP` is checked first and
Cloudflare overwrites it, so for all real traffic the value is trustworthy. The
forgeable `X-Forwarded-For` fallback is only reached when `CF-Connecting-IP` is
absent — which, given a CF-only origin, means never.

**The dependency is load-bearing and implicit.** The safety of app-wide rate
limiting, IP bans and geoblocking rests entirely on the origin being
unreachable except through Cloudflare. Nothing in the code says so, and nothing
tests it.

### Recommended hardening

Change the fallback from the raw header to `request.remote_addr`:

```python
ip = request.headers.get("CF-Connecting-IP") or request.remote_addr
```

In the current topology this is a **no-op** — `CF-Connecting-IP` is always
present, so the fallback never runs. Its value is removing the implicit
dependency: if the origin is ever exposed directly, misconfigured, or moved off
Cloudflare, the code degrades to a trustworthy source instead of a forgeable one.

Do **not** apply it blindly. `ProxyFix` is configured `x_for=1`, i.e. trust
exactly one proxy hop. If the hop count between Cloudflare and the app ever
changes, `remote_addr` resolves to the wrong entry — and because it is the
rate-limiter key, every user could collapse into a single shared bucket, which
is an outage rather than a vulnerability. Verify the hop count first:

```bash
# what the app actually sees for a real request
docker compose exec web uv run --no-sync python -c "
from flask import request
# log request.remote_addr, request.headers.get('X-Forwarded-For'),
# and request.headers.get('CF-Connecting-IP') from a live request handler"
```

---

## When adding code that uses a client IP

1. Use `request.remote_addr`, or `CF-Connecting-IP` if you specifically need the
   original client behind Cloudflare.
2. Never parse the leftmost `X-Forwarded-For` entry.
3. If the IP gates access — allowlist, ban, geoblock, rate limit — add a
   regression test that sends a forged header from a disallowed peer and asserts
   it is still rejected. `tests/security/test_admin_ip_allowlist.py` is the
   pattern.
