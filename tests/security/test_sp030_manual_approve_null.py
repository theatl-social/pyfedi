"""SP-030 — a NULL ap_manually_approves_followers must mean auto-accept.

``user.ap_manually_approves_followers`` is ``nullable=True`` with **no server
default**; the ``default=False`` on the model is applied by SQLAlchemy on ORM
insert only. Rows predating the column, or created outside the ORM, are NULL.

Upstream PieFed v1.7.11 introduced a third, inconsistent reading of it:

===========================================  ==================  ============
site                                         expression          NULL means
===========================================  ==================  ============
``shared/user.py`` ``follow_user()``         ``is True``         auto-accept
``user/routes.py`` profile UI                truthiness          auto-accept
``activitypub/routes.py`` inbox (v1.7.11)    ``is False``        **pending**
===========================================  ==================  ============

For a NULL row that means local follows are accepted immediately while remote
follows silently queue in ``/user/follow_requests`` -- a page the user has no
reason to visit, since they never turned manual approval on. Their follower
count simply stops growing, with no error anywhere.

NULL can only mean "never expressed a preference", which is the column's
documented default of False. The inbox is the outlier and now reads
``is not True``, matching ``follow_user()``.

A companion data migration (``20260817_manual_approve_backfill``) removes the
NULLs for local users so a future reader cannot reintroduce the divergence.
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
AP_ROUTES = REPO_ROOT / "app" / "activitypub" / "routes.py"
SHARED_USER = REPO_ROOT / "app" / "shared" / "user.py"
MIGRATION = (
    REPO_ROOT
    / "migrations"
    / "versions"
    / "20260817_manual_approve_backfill.py"
)


def test_inbox_treats_null_as_auto_accept():
    src = AP_ROUTES.read_text()
    assert "local_user.ap_manually_approves_followers is not True" in src, (
        "the inbox Follow handler must read the flag as `is not True` so a "
        "NULL column auto-accepts, matching follow_user()"
    )
    assert "ap_manually_approves_followers is False" not in src, (
        "upstream's `is False` reading is back: a NULL column would route "
        "remote followers into a pending queue while local follows auto-accept"
    )


def test_local_follow_path_still_reads_is_true():
    """The two paths must agree; this pins the side we aligned to."""
    src = SHARED_USER.read_text()
    assert "to_follow.ap_manually_approves_followers is True" in src


def test_explicit_true_still_requires_approval():
    """Guard against 'fixing' NULL by disabling manual approval entirely."""
    src = AP_ROUTES.read_text()
    # `is not True` is False exactly when the column is True -> no auto-accept.
    assert "auto_accept" in src
    assert "is_accepted=True if auto_accept else None" in src, (
        "a request that is not auto-accepted must be recorded as pending "
        "(None), not accepted or rejected"
    )


def test_backfill_migration_exists_and_is_scoped_to_local_users():
    assert MIGRATION.exists(), "the NULL backfill migration is missing"
    src = MIGRATION.read_text()
    assert "ap_manually_approves_followers = false" in src
    assert "ap_id IS NULL" in src, (
        "the backfill must be scoped to local users -- for remote actors NULL "
        "means 'no value seen in their actor JSON', which is not False"
    )


def test_backfill_migration_is_syntactically_valid():
    ast.parse(MIGRATION.read_text())
