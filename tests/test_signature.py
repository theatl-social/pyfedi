"""HTTP signature digest and signature-header round-trip tests.

Ported from upstream v1.7.8 `tests/test_signature.py`, which ships as a bare
script (module-level asserts plus `print('Done')`) rather than a pytest module.
Taken verbatim it aborts collection of the whole suite: every `testing_data/`
fixture ends with a trailing newline, but the stored `digest_N` values were
computed over the newline-stripped bodies, so `digest_N == calculate_digest(...)`
is false upstream too. Strip the fixtures and express the same checks as tests.
"""

import pytest

from app.activitypub.signature import HttpSignature
from app.utils import file_get_contents


def _fixture(name):
    return file_get_contents(f"testing_data/{name}").rstrip("\n")


@pytest.mark.parametrize("n", [1, 2, 3])
def test_calculate_digest_matches_stored_digest(n):
    """calculate_digest() reproduces the digest recorded alongside each body."""
    body = _fixture(f"body_{n}.json")
    expected = _fixture(f"digest_{n}")

    assert HttpSignature.calculate_digest(body.encode()) == expected


@pytest.mark.parametrize("n", [1, 2, 3])
def test_signature_parse_compile_round_trip(n):
    """parse_signature() -> compile_signature() preserves every field."""
    signature = _fixture(f"signature_{n}")

    parsed = HttpSignature.parse_signature(signature)
    recompiled = HttpSignature.compile_signature(parsed)

    assert sorted(recompiled.split(",")) == sorted(signature.split(","))
