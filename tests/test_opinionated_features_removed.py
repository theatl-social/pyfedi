"""Owner policy: upstream content/account classifiers and suspicion tools stay out.

Schema columns and historical notifications remain compatible. Executable
classification, filtering, account challenges, and the accompanying controls
are removed, including tools that only suggest accounts for investigation.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted((ROOT / "app").rglob("*.py")) + [ROOT / "config.py"]
TEMPLATES = sorted((ROOT / "app/templates").rglob("*.html"))


@pytest.mark.parametrize("attribute", ["reposter", "reposter_override", "ignore_reposters", "from_reposter", "liability"])
def test_classifier_columns_are_never_used_at_runtime(attribute):
    offenders = [
        f"{path.relative_to(ROOT)}:{node.lineno}"
        for path in SOURCES
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Attribute) and node.attr == attribute
    ]
    assert not offenders, f"Runtime classification/filtering is back: {offenders}"


@pytest.mark.parametrize("identifier", [
    "bot_challenge_user", "user_bot_challenge", "bot_challenge",
    "check_expired_bot_challenges", "pwn_bots", "bot_challenge_result", "vote_manipulation_findings",
    "admin_votes", "admin_votes_for_noone", "admin_votes_serial_downvoters",
    "voting_clusters", "user_voting_patterns", "user_voting_patterns_down",
    "user_post_timing", "_get_user_same_name",
])
def test_opinionated_tools_have_no_executable_entry_points(identifier):
    offenders = [
        f"{path.relative_to(ROOT)}:{node.lineno}"
        for path in SOURCES
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == identifier
    ]
    assert not offenders, f"Opinionated review/challenge tool is back: {offenders}"


@pytest.mark.parametrize("needle", [
    "ignore_reposters", "reposter_override", "user.reposter", "from_reposter",
    "filter='liability'", "bot_challenge", "voting_patterns", "post_timing",
    "posting_pattern", "comment_pattern", "same_user_name", "admin_votes",
])
def test_templates_have_no_classifier_controls_or_suspicion_tools(needle):
    offenders = [str(p.relative_to(ROOT)) for p in TEMPLATES if needle in p.read_text()]
    assert not offenders, f"Opinionated UI is back: {offenders}"


def test_no_external_image_content_classifier():
    needle = "CHAN_DETECTION" + "_ENDPOINT"
    offenders = [str(p.relative_to(ROOT)) for p in SOURCES if needle in p.read_text()]
    assert not offenders, f"External image-content classifier is back: {offenders}"


def test_new_accounts_are_not_automatically_held_for_post_review():
    tree = ast.parse((ROOT / "app/utils.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "finalize_user_setup")
    assert not any(
        isinstance(n, ast.Attribute) and n.attr == "ban_posts"
        for n in ast.walk(fn)
    ), "New-account post probation is back"


def test_removed_tools_are_not_registered():
    from app import create_app
    from tests.conftest import TestConfig

    app = create_app(TestConfig)
    removed = {
        "main.bot_challenge", "main.bot_challenge_result", "user.user_bot_challenge",
        "user.user_voting_patterns", "user.user_voting_patterns_down",
        "user.user_post_timing", "admin.admin_votes",
        "admin.admin_votes_for_noone", "admin.admin_votes_serial_downvoters",
    }
    assert not (removed & app.view_functions.keys())
    assert "voting_clusters" not in app.cli.commands


def test_content_review_has_no_score_or_account_age_inferences():
    tree = ast.parse((ROOT / "app/admin/routes.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "admin_content")
    assert not any(isinstance(n, ast.Attribute) and n.attr in {"score", "down_votes", "created"} for n in ast.walk(fn))
    ui = (ROOT / "app/templates/admin/content.html").read_text()
    assert 'value="trash"' not in ui and 'value="spammy"' not in ui
