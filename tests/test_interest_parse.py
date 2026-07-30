"""Tests for app.cli.parse_communities against the shipped interests.txt.

Ported from upstream v1.7.8 `tests/test_interest_parse.py`, which ships as a
bare script that calls parse_communities three times and prints the results
without asserting anything, so pytest collects zero tests from it. Same inputs,
expressed as real assertions.
"""

import pytest

from app.cli import parse_communities
from app.utils import file_get_contents


@pytest.fixture(scope="module")
def interests():
    return file_get_contents("interests.txt")


@pytest.mark.parametrize("segment", ["gaming", "chilling", "mental health"])
def test_segment_returns_only_its_own_community_urls(interests, segment):
    """Each segment yields a non-empty block of indented community URLs."""
    communities = parse_communities(interests, segment)
    lines = [line for line in communities.split("\n") if line]

    assert lines, f"segment {segment!r} produced no communities"
    assert all(line.startswith("https://") for line in lines)
    # The segment heading itself is a delimiter, never part of the output.
    assert segment not in lines


def test_unknown_segment_returns_nothing(interests):
    assert parse_communities(interests, "no-such-segment-exists") == ""


def test_segments_do_not_bleed_into_each_other(interests):
    """A blank line ends a segment, so segments must not share entries."""
    gaming = set(filter(None, parse_communities(interests, "gaming").split("\n")))
    chilling = set(filter(None, parse_communities(interests, "chilling").split("\n")))

    assert gaming and chilling
    assert gaming != chilling
