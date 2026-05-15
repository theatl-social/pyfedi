"""SP-014 regression: community_view variants 3/4/5/6 must refuse to render
private-community details for non-members.

Mirrors Lemmy GHSA-95q8-x6r6-672m. The full /community/* API endpoints
(variant 3 = get-community, variant 4 = follow, variant 5 = block,
variant 6 = resolve-object) include description, posting_warning, banner,
sidebar, moderator list — none of which a non-member of a private
community should see.

Structural test (AST-based) — no Flask app context needed.
"""

import ast
import pathlib

VIEWS = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "alpha" / "views.py"
)


def _function_source(name):
    src = VIEWS.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {VIEWS}")


def test_community_view_gates_variants_3_to_6():
    """The full-response variants must check private + membership."""
    src = _function_source("community_view")
    # Look for the canonical pattern: private + community_membership_private
    has_private_check = (
        "community.private" in src and "community_membership_private" in src
    )
    assert has_private_check, (
        "SP-014 REGRESSION: community_view no longer references "
        "community.private and community_membership_private together. "
        "Private community sidebar / modlist may leak to non-members."
    )


def test_community_view_check_covers_full_variants():
    """The check must cover variants 3, 4, 5, 6 (the 'full info' responses).

    We assert structurally: the offset of the FIRST occurrence of
    `community.private` in the function source must precede the offset of
    the first `variant == 3` branch — so the gate fires before any
    full-data variant builds its dict.
    """
    src = _function_source("community_view")
    private_offset = src.find("community.private")
    variant_3_offset = src.find("variant == 3")
    membership_offset = src.find("community_membership_private")
    assert (
        private_offset != -1
    ), "SP-014 REGRESSION: community.private check not found in community_view"
    assert (
        membership_offset != -1
    ), "SP-014 REGRESSION: community_membership_private check not found in community_view"
    if variant_3_offset != -1:
        assert private_offset < variant_3_offset, (
            f"SP-014 REGRESSION: private check appears AFTER variant-3 branch "
            f"(offset {private_offset} vs {variant_3_offset}). Variant 3 may "
            f"still leak before the check fires."
        )
