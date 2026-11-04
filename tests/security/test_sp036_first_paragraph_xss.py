"""SP-036 regression: first_paragraph() turned escaped text into live HTML.

Post teasers render ``{{ first_paragraph(post.body_html) | safe }}``. When a
body's first paragraph is boilerplate ("Summary", "Comments", "cross-posted
from: ...") the function returns the *second* paragraph as
``f'<p>{second_paragraph.text}</p>'``. BeautifulSoup's ``.text`` decodes
entities, so a stored ``&lt;img src=x onerror=...&gt;`` -- which is inert text
in body_html -- came back as a real ``<img onerror>`` element on every feed
page. Reachable by any local user (markdown ``\\<img ...>``) or federated post.
The other branch was already wrapped in allowlist_html(); this one never was,
in this fork or upstream (still present in v1.8.11).
"""

import pytest

from app import create_app
from config import Config


class _TestConfig(Config):
    TESTING = True
    CACHE_TYPE = "NullCache"


@pytest.fixture(scope="module")
def app_ctx():
    app = create_app(_TestConfig)
    with app.app_context():
        yield


PAYLOADS = [
    "&lt;img src=x onerror=alert(document.cookie)&gt;",
    "&lt;script&gt;alert(1)&lt;/script&gt;",
    "&lt;a href=&quot;javascript:alert(1)&quot;&gt;x&lt;/a&gt;",
]
LEADERS = ["Summary", "*Summary*", "Comments", "Cross-posted from: https://example.com/post/1"]


@pytest.mark.parametrize("leader", LEADERS)
@pytest.mark.parametrize("payload", PAYLOADS)
def test_second_paragraph_text_is_not_reinterpreted_as_html(app_ctx, leader, payload):
    from app.utils import first_paragraph

    out = first_paragraph(f"<p>{leader}</p><p>{payload}</p>")
    assert "<img" not in out and "<script" not in out and "<a " not in out, (
        f"SP-036 REGRESSION: first_paragraph() emitted live HTML from escaped text: {out!r}"
    )
    # The text itself still shows, escaped.
    assert out.startswith("<p>") and "&lt;" in out


def test_ordinary_second_paragraph_still_returned(app_ctx):
    from app.utils import first_paragraph

    assert first_paragraph("<p>Summary</p><p>Fish &amp; chips</p>") == "<p>Fish &amp; chips</p>"
