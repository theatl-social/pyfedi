"""SSRF (Server-Side Request Forgery) guard for outbound HTTP requests.

SP-002 — see SECURITY_PATCHES.md.

ActivityPub federation makes outbound HTTP calls to URLs taken from untrusted
remote JSON (actor profiles, object IDs, webfinger self-links, image URLs,
nodeinfo links, instance domains). Without validation, an attacker can point
those URLs at internal addresses (127.0.0.1, RFC1918, link-local, cloud
metadata endpoints) and exfiltrate internal state via response bodies that get
persisted to disk/DB.

This module validates the destination of every outbound HTTP request before it
fires, and validates each hop in any redirect chain. It is intended to wrap
the single httpx-based outbound HTTP boundary, `app.utils.get_request`.

Known residual risk (DNS rebinding TOCTOU): we resolve DNS to validate the
host, then httpx does its own DNS resolution at fetch time. An attacker
controlling a DNS server can return a public IP for the first lookup and a
private IP for the second. Closing this fully requires a custom httpx
transport that pre-resolves and dials by IP while preserving SNI/Host. That
is a follow-up; the current guard catches direct attacks (IP literals in URLs,
public-IP redirects to private targets, cloud-metadata literals).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse


_BLOCKED_HOST_LITERALS: frozenset[str] = frozenset(
    {
        # AWS / GCP / Azure / DigitalOcean metadata endpoint
        "169.254.169.254",
        # AWS IPv6 metadata endpoint
        "fd00:ec2::254",
        # Alibaba Cloud metadata endpoint
        "100.100.100.200",
        # Oracle Cloud metadata endpoint
        "192.0.0.192",
    }
)

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})
_ALLOWED_SCHEMES_DEV: frozenset[str] = frozenset({"http", "https"})

_MAX_REDIRECTS = 10


class SsrfBlocked(Exception):
    """Raised when a URL fails the SSRF guard."""


def validate_outbound_url(
    url: str, *, allow_private: bool = False, allow_http: bool = False
) -> tuple[str, list[str]]:
    """Validate that ``url`` is safe to fetch from an SSRF perspective.

    Returns ``(hostname, [resolved_ip_str, ...])`` on success.
    Raises ``SsrfBlocked`` on rejection.

    Checks performed:
      * scheme is https (or http if ``allow_http=True``)
      * hostname is present
      * hostname resolves via DNS
      * none of the resolved IPs are in the cloud-metadata literal blocklist
      * unless ``allow_private=True``: none of the resolved IPs are private,
        loopback, link-local, multicast, reserved, or unspecified
    """
    parsed = urlparse(url)
    schemes = _ALLOWED_SCHEMES_DEV if allow_http else _ALLOWED_SCHEMES
    if parsed.scheme.lower() not in schemes:
        raise SsrfBlocked(
            f"scheme {parsed.scheme!r} not allowed (allowed: {sorted(schemes)})"
        )
    host = parsed.hostname
    if not host:
        raise SsrfBlocked("url has no hostname")

    # Reject the cloud-metadata literals at the host level too — covers the
    # case where a user sends "http://169.254.169.254/..." directly.
    if host in _BLOCKED_HOST_LITERALS:
        raise SsrfBlocked(f"host {host!r} is in the cloud-metadata blocklist")

    ip_list = _resolve_host(host)

    if not allow_private:
        for ip in ip_list:
            ip_str = str(ip)
            if ip_str in _BLOCKED_HOST_LITERALS:
                raise SsrfBlocked(
                    f"host {host!r} resolves to {ip_str} which is in the cloud-metadata blocklist"
                )
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise SsrfBlocked(
                    f"host {host!r} resolves to {ip_str} which is non-public"
                )
    return host, [str(ip) for ip in ip_list]


def _resolve_host(host: str) -> list[ipaddress._BaseAddress]:
    """Resolve a hostname or IP-literal to a list of ipaddress objects.

    Raises SsrfBlocked on resolution failure.
    """
    # Try parsing as a literal IP first (covers numeric-IP URLs).
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise SsrfBlocked(f"DNS resolution failed for {host!r}: {e}")

    out: list[ipaddress._BaseAddress] = []
    for entry in addr_info:
        try:
            out.append(ipaddress.ip_address(entry[4][0]))
        except (ValueError, IndexError):
            continue

    if not out:
        raise SsrfBlocked(f"no IPs resolved for {host!r}")
    return out


def safe_httpx_head(
    client,
    url: str,
    *,
    allow_private: bool = False,
    allow_http: bool = False,
    **kwargs,
):
    """httpx HEAD with SSRF validation. SP-016.

    HEAD doesn't return a body, but an attacker can still learn open-vs-closed
    ports, response headers (Server, X-Powered-By, etc.), and infer service
    presence on internal addresses. Same destination validation as
    ``safe_httpx_get``. Redirects are NOT followed for HEAD by default — if a
    caller passes ``follow_redirects=True``, the underlying client decides
    (httpx defaults to no-redirects for HEAD).
    """
    validate_outbound_url(url, allow_private=allow_private, allow_http=allow_http)
    return client.head(url, **kwargs)


def safe_httpx_get(
    client,
    url: str,
    *,
    follow_redirects: bool = False,
    allow_private: bool = False,
    allow_http: bool = False,
    **kwargs,
):
    """httpx GET with per-hop SSRF validation.

    ``client`` is an ``httpx.Client``. We don't import httpx at module level
    so this module stays lightweight enough to import in tests without httpx.

    When ``follow_redirects=True``, redirects are followed manually so each
    hop is validated. Maximum chain length is ``_MAX_REDIRECTS``.
    """
    validate_outbound_url(url, allow_private=allow_private, allow_http=allow_http)

    if not follow_redirects:
        return client.get(url, follow_redirects=False, **kwargs)

    current_url = url
    for _ in range(_MAX_REDIRECTS):
        resp = client.get(current_url, follow_redirects=False, **kwargs)
        if not (300 <= resp.status_code < 400):
            return resp
        location = resp.headers.get("Location")
        if not location:
            return resp
        next_url = urljoin(current_url, location)
        validate_outbound_url(
            next_url, allow_private=allow_private, allow_http=allow_http
        )
        current_url = next_url

    raise SsrfBlocked(f"too many redirects (>{_MAX_REDIRECTS}) starting from {url!r}")
