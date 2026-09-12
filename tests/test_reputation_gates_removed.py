"""Guard: account-age / reputation gates and the community-name word list stay out.

Removed by owner decision on 2026-09-12, as the second pass of the heuristics
cleanup (see `tests/test_content_heuristics_removed.py`). Each restricted what a
person could do from their account age, vote-derived reputation, or voting
pattern -- none of which is evidence about the action being taken:

- `can_downvote()`: no downvoting at reputation < -10, or with a negative
  "attitude" (having cast more downvotes than upvotes over 10+ votes).
- `User.can_send_pm_to()`: no PMs from accounts under 24h old or at
  reputation <= -10. The explicit gates stay: banned, unverified, and the
  per-user `can_send_pm` flag.
- `trustworthy_account_required` on starting a chat, plus inline
  `trustworthy()` checks on suggesting topics and viewing the banned-tags list:
  accounts under 7 days old with reputation < 100 were refused. (The
  banned-domains list never had this gate, so the two pages now match.)
- `aged_account_required` on creating a local community, and the inline
  "account is too new" refusal on inviting people to a community.
- `can_create_post()`: remote accounts under 24h old limited to 3 posts.
- `is_bad_name()`: a substring swear-word list that silently skipped
  communities during admin bulk import and `flask` CLI preload. Substring
  matching made it Scunthorpe-prone ("petits" contains "tits").

Deliberately KEPT, and asserted below so a later cleanup does not quietly
change them:

- `User.trustworthy()` itself, because community wiki pages offer a
  moderator-chosen "trusted" edit tier (`who_can_edit == 1`) defined by it.
- Owner chose to keep: dropping DMs from remote senders under 24h old, purging
  content when a remote account under 24h old deletes itself, and the
  reputation warning icons beside usernames.
"""

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "app"
SOURCE_FILES = sorted(APP.rglob("*.py")) + [REPO_ROOT / "config.py", REPO_ROOT / "pyfedi.py"]


def _tree(relpath):
    return ast.parse((REPO_ROOT / relpath).read_text(encoding="utf-8"))


def _function_source(relpath, name, cls=None):
    tree = _tree(relpath)
    body = tree.body
    if cls:
        body = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls).body
    fn = next((n for n in body if isinstance(n, ast.FunctionDef) and n.name == name), None)
    assert fn is not None, f"{cls + '.' if cls else ''}{name}() not found in {relpath}"
    return ast.unparse(fn)


def _references(needle):
    return [
        f"{p.relative_to(REPO_ROOT)}:{n}"
        for p in SOURCE_FILES
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if needle in line
    ]


def test_downvoting_not_gated_on_reputation_or_attitude():
    src = _function_source("app/utils.py", "can_downvote")
    assert "reputation" not in src and "attitude" not in src, (
        "can_downvote() gates on reputation/attitude again."
    )


def test_pms_not_gated_on_account_age_or_reputation():
    src = _function_source("app/models.py", "can_send_pm_to", cls="User")
    assert "created_very_recently" not in src and "reputation" not in src, (
        "User.can_send_pm_to() gates on account age/reputation again."
    )
    for kept in ("banned", "verified", "can_send_pm"):
        assert kept in src, f"can_send_pm_to() lost its explicit `{kept}` gate"


def test_remote_posts_not_gated_on_account_age():
    src = _function_source("app/utils.py", "can_create_post")
    assert "created_very_recently" not in src, (
        "can_create_post() limits new remote accounts again."
    )


def test_no_age_or_trust_decorators():
    for name in ("trustworthy_account_required", "aged_account_required"):
        hits = _references(name)
        assert not hits, f"{name} is back at {hits}"


def test_topic_suggestions_and_banned_tags_not_trust_gated():
    for relpath, name in (("app/topic/routes.py", "suggest_topics"),
                          ("app/tag/routes.py", "tags_blocked_list")):
        assert "trustworthy" not in _function_source(relpath, name), (
            f"{name}() is gated on trustworthy() again."
        )


def test_community_invite_not_gated_on_account_age():
    hits = [h for h in _references("created_very_recently") if h.startswith("app/community/routes.py")]
    assert not hits, f"community routes gate on account age again at {hits}"


def test_no_community_name_word_list():
    hits = _references("is_bad_name")
    assert not hits, f"The community-name swear-word substring list is back at {hits}"


def test_kept_wiki_trusted_tier_still_uses_trustworthy():
    """Removing trustworthy() would silently change a tier moderators chose."""
    src = _function_source("app/models.py", "can_edit", cls="CommunityWikiPage")
    assert "trustworthy()" in src
    _function_source("app/models.py", "trustworthy", cls="User")
