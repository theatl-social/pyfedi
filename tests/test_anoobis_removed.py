"""Guard: the upstream "anoobis" proof-of-work gate stays out of this fork.

Upstream PieFed introduced anoobis in v1.7.10 (`ba42e38e` and follow-ups): a
`check_anoobis` decorator that bounced anonymous visitors to `/anoobis`, where
JavaScript brute-forced a SHA-256 nonce before setting a cookie and continuing.

This fork removed it deliberately during the v1.7.10 merge, for two reasons:

1. **The work is never verified.** `anoobis.html` called `solveProofOfWork()`
   and discarded the return value, then set `anoobis=ok` unconditionally.
   Nothing was ever sent to the server and no endpoint validated a solution;
   `check_anoobis` only tested `request.cookies.get('anoobis') is None`. So the
   real gate was "present any cookie named anoobis", which `curl -b anoobis=x`
   satisfies. It cost real users CPU and cost a scraper one cookie. The
   User-Agent whitelist was likewise satisfied by claiming to be Googlebot.
2. It shipped an open redirect: `next` was validated with `furl(next).host`,
   which reports no host for `/\\evil.com`, but browsers normalise backslashes
   to forward slashes, yielding protocol-relative `//evil.com`.

This file exists because the fork has a history of upstream features silently
returning on subsequent merges (see `tests/test_post_slug.py`, which guards
`Post.generate_ap_id` after three consecutive regressions). If a future merge
reintroduces anoobis, these fail rather than quietly re-enabling it.

If anoobis is ever wanted, delete this file in the same commit that adds it
back — with server-side verification of the proof.
"""

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "app"

PY_FILES = sorted(APP.rglob("*.py"))
TEMPLATES = sorted((APP / "templates").rglob("*.html"))


def test_no_check_anoobis_decorator():
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in PY_FILES
        if "check_anoobis" in p.read_text()
    ]
    assert not offenders, (
        "anoobis has been reintroduced into "
        f"{offenders}. It was removed deliberately: the proof-of-work result "
        "was never verified server-side, so the gate reduced to 'present any "
        "cookie named anoobis'. See this module's docstring."
    )


def test_no_anoobis_route():
    routes = APP / "main" / "routes.py"
    src = routes.read_text()
    assert "/anoobis" not in src, (
        "The /anoobis route is back in app/main/routes.py. It also carried an "
        "open redirect via the `next` parameter (furl reports no host for "
        r"'/\evil.com', which browsers normalise to '//evil.com')."
    )


def test_no_anoobis_template():
    assert not (APP / "templates" / "anoobis.html").exists(), (
        "app/templates/anoobis.html is back. This template ran an unverified "
        "client-side proof of work and then set the bypass cookie itself."
    )


def test_no_anoobis_config():
    config_src = (REPO_ROOT / "config.py").read_text()
    assert "ANOOBIS" not in config_src, (
        "ANOOBIS settings are back in config.py. Note upstream's version read "
        "os.environ.get('') — an empty key — for both difficulty values, so "
        "neither could ever be configured."
    )


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_no_template_references_anoobis(template):
    assert "anoobis" not in template.read_text().lower(), (
        f"{template.relative_to(REPO_ROOT)} references anoobis."
    )
