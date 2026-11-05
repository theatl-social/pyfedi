"""Guard: hidden anti-LLM payloads stay out of rendered pages.

Upstream ed8d40aca ("magic string that chokes claude") put a visually-hidden
paragraph into post/post.html containing a published refusal-trigger string,
so any AI tool reading a post page -- a summariser, a screen-reading agent, an
assistant a member points at a thread -- stops working on it. People never
see it. Removed by owner decision (2026-11-04), alongside the earlier AI
detection and heuristic removals.

This scans every template and static JS/CSS file, so the same payload moved to
another page, or a different trigger string with the same naming, also fails.
"""

import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

# Matches the published refusal-trigger family and generic prompt-injection
# phrasing aimed at language models. Kept as fragments so this file does not
# itself carry a working trigger string.
PATTERNS = [
    re.compile(r"MAGIC_STRING_TRIGGER", re.I),
    re.compile(r"TRIGGER_REFUSAL", re.I),
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
]


def _files():
    for sub in ("templates", "static"):
        for path in (APP / sub).rglob("*"):
            if path.suffix in {".html", ".js", ".css", ".txt", ".xml", ".json"} and path.is_file():
                yield path


def test_no_hidden_llm_refusal_or_injection_strings():
    offenders = []
    for path in _files():
        text = path.read_text(errors="ignore")
        for pat in PATTERNS:
            if pat.search(text):
                offenders.append(f"{path.relative_to(APP.parent)}: {pat.pattern}")
    assert not offenders, f"Anti-LLM payload is back: {offenders}"


# --- AI crawler policy (owner decision 2026-11-04) ---------------------------
#
# Upstream shipped, on unless ALLOW_AI_CRAWLERS was set: robots.txt blocks for
# AI crawlers and agents, a `Content-Signal: ai-train=no, ai-input=no` line, an
# RSL licence at /rsl.xml, and a `Link: rel="license"` header on every response.
# All removed. Generic SEO-bot blocks and path disallows in robots.txt stay.

REPO = APP.parent
AI_AGENTS = [
    "GPTBot", "ClaudeBot", "Claude-SearchBot", "anthropic-ai", "Bytespider",
    "PerplexityBot", "meta-externalagent", "meta-externalfetcher",
    "meta-webindexer", "DuckAssistBot", "LinkupBot", "Lightpanda",
]


def test_robots_txt_does_not_target_ai_agents():
    robots = (APP / "templates" / "robots.txt").read_text()
    lowered = robots.lower()
    back = [a for a in AI_AGENTS if a.lower() in lowered]
    assert not back, f"AI-agent blocks are back in robots.txt: {back}"
    assert "content-signal" not in lowered, "Content-Signal AI opt-out is back in robots.txt"
    assert "rsl" not in lowered, "RSL licence reference is back in robots.txt"


def test_rsl_licence_and_setting_are_gone():
    assert not (APP / "templates" / "rsl.xml").exists(), "templates/rsl.xml is back"
    for rel in ("pyfedi.py", "config.py", "profile_app.py", "env.sample", "app/main/routes.py"):
        path = REPO / rel
        if path.exists():
            text = path.read_text()
            assert "ALLOW_AI_CRAWLERS" not in text, f"ALLOW_AI_CRAWLERS is back in {rel}"
            assert "rsl.xml" not in text, f"rsl.xml is referenced again in {rel}"


def test_rsl_route_not_registered():
    from app import create_app
    from config import Config

    class _C(Config):
        TESTING = True
        CACHE_TYPE = "NullCache"

    app = create_app(_C)
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/rsl.xml" not in rules
