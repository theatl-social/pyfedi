"""SP-012 regression: SECRET_KEY known-bad check must be case- and
whitespace-insensitive.

SP-003's known-bad list was exact-match, so 'YOU-WILL-NEVER-GUESSS' (the
typical all-caps form in docs) bypassed validation. Operators commonly
copy SECRET_KEY values with capitalization or surrounding whitespace
artifacts; normalizing before the membership check eliminates that class
of misconfiguration.
"""

import pytest

from app import _validate_secret_key


@pytest.mark.parametrize(
    "variant",
    [
        "YOU-WILL-NEVER-GUESSS",  # uppercase
        "You-Will-Never-Guesss",  # mixed case
        " you-will-never-guesss ",  # whitespace padding
        "\tyou-will-never-guesss\n",  # tab + newline
        "CHANGE-ME",
        "Change-Me",
        "Secret",
        " DEV ",
    ],
)
def test_known_default_variants_rejected(variant):
    with pytest.raises(RuntimeError, match=r"SP-003.*known-default"):
        _validate_secret_key(variant)


def test_long_unique_key_still_accepted():
    """Make sure normalization didn't break the happy path."""
    _validate_secret_key("an-actually-strong-32-plus-char-key-here-please")
