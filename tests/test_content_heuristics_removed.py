"""Guard: upstream's surface-signal content heuristics stay out of this fork.

Removed deliberately on 2026-09-12, alongside the AI detectors guarded by
`tests/test_ai_detection_removed.py`. Each judged people or content from a
superficial signal and then acted on that judgment:

- **Em-dash report** (admin setting, *on* by default). Any comment containing
  an em dash from an account under 24h old filed an automated "likely AI"
  report against the author. Em dashes are ordinary punctuation, inserted
  automatically by phone keyboards and word processors.
- **OCR "4chan screenshot" filter** (`enable_chan_image_filter`). Ran
  Tesseract over uploaded images, rejecting any whose text contained
  "Anonymous" and "No."; for remote posts in low-quality communities it filed
  a "Review this" report. It matches any screenshot of anything with those two
  words, and added OCR of untrusted images -- plus `pytesseract` and the
  Tesseract packages -- to the image pipeline.
- **"this" comment filter** (`enable_this_comment_filter`). Rejected any
  comment whose whole body was "this", "this." or "this!" -- with an error for
  local users, silently for federated ones (`PostReply.new()` serves web, API,
  inbox and import alike).
- **GIF reply filter** (`enable_gif_reply_rep_decrease`). Rejected comments
  consisting of a tenor/giphy/imgflip link, the same way.
- **"memes"/"shitpost" name -> low quality** (`meme_comms_low_quality`). Any
  community whose name contained those substrings was marked low-quality, so
  its upvotes stopped counting toward reputation. The API creation path
  ignored the setting and applied the substring test unconditionally.

What stays: the `Site` columns behind these settings (schema is immutable per
CLAUDE.md -- they are simply no longer read), `Community.low_quality` and the
per-community admin toggle for it, users' own keyword filters, admin-configured
domain warnings and blocked-image hashes, and account-age / reputation rate
limits, which are a separate decision.

Assertions match identifiers, so a comment in `app/` naming one of these trips
them -- reword the comment rather than weakening the guard.
"""

import pathlib
import re
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "app"
SOURCE_FILES = sorted(APP.rglob("*.py")) + [REPO_ROOT / "config.py", REPO_ROOT / "pyfedi.py"]
TEMPLATES = sorted((APP / "templates").rglob("*.html"))

# Immutable-schema column definitions are allowed to remain; nothing else.
COLUMN_DEFINITION = re.compile(r"^\s*\w+\s*=\s*db\.Column\(")


def _references(needle, files):
    hits = []
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if needle in line and not COLUMN_DEFINITION.match(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    return hits


@pytest.mark.parametrize(
    "needle, why",
    [
        ("enable_report_em_dash_replies", "em-dash 'likely AI' auto-report"),
        ("limit_one_em_report_per_user", "em-dash 'likely AI' auto-report"),
        ("em-dash_used_by_", "em-dash report dedupe cache"),
        ("enable_chan_image_filter", "OCR '4chan screenshot' filter"),
        ("pytesseract", "OCR '4chan screenshot' filter"),
        ("ALLOW_4CHAN", "OCR '4chan screenshot' filter"),
        ("enable_this_comment_filter", "'this' comment filter"),
        ("reply_is_low_effort", "'this' comment filter"),
        ("enable_gif_reply_rep_decrease", "GIF reply filter"),
        ("reply_is_just_link_to_gif_reaction", "GIF reply filter"),
        ("meme_comms_low_quality", "community-name low-quality heuristic"),
    ],
)
def test_heuristic_not_referenced(needle, why):
    hits = _references(needle, SOURCE_FILES + TEMPLATES)
    assert not hits, f"{why} is back ({needle!r}) at: {hits}. See this module's docstring."


def test_ocr_report_subtype_no_longer_created():
    """Source only: `user/notifs/20.html` must keep rendering this subtype,
    because notification rows created before the removal still exist."""
    hits = _references("post_with_suspicious_image", SOURCE_FILES)
    assert not hits, f"Code creates OCR '4chan screenshot' reports again at: {hits}"


def test_no_community_name_substring_marks_low_quality():
    pattern = re.compile(r"""["'](memes|shitpost)["']\s+in\b""")
    hits = [
        f"{p.relative_to(REPO_ROOT)}:{n}"
        for p in SOURCE_FILES
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert not hits, (
        f"A community-name substring test is back at {hits}. Names containing "
        "'memes' or 'shitpost' were auto-marked low-quality, zeroing reputation "
        "from their upvotes."
    )


def test_pytesseract_not_a_dependency():
    deps = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    assert not [d for d in deps if d.lower().startswith("pytesseract")]
    assert 'name = "pytesseract"' not in (REPO_ROOT / "uv.lock").read_text(encoding="utf-8"), (
        "pytesseract is still in uv.lock -- run `uv lock`."
    )


def test_tesseract_not_installed_in_image():
    assert "tesseract" not in (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8"), (
        "The Dockerfile installs Tesseract again; it only existed for the OCR filter."
    )


def test_admin_form_has_no_heuristic_fields():
    """Behavioural: the admin settings form no longer offers these toggles."""
    from app.admin import forms

    removed = {
        "enable_report_em_dash_replies", "limit_one_em_report_per_user",
        "enable_chan_image_filter", "enable_this_comment_filter",
        "enable_gif_reply_rep_decrease", "meme_comms_low_quality",
    }
    offenders = sorted(
        f"{name}.{field}"
        for name, cls in vars(forms).items()
        if isinstance(cls, type)
        for field in removed
        if field in vars(cls)
    )
    assert not offenders, f"Admin forms still expose removed heuristic toggles: {offenders}"
