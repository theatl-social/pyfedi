"""Backfill NULL ap_manually_approves_followers for local users

`user.ap_manually_approves_followers` is nullable with no server default; the
`default=False` on the model is applied by SQLAlchemy on ORM insert only. Rows
that predate the column, or that were created outside the ORM, are therefore
NULL.

That was harmless until upstream v1.7.11, which reads the column in the
federated Follow handler as `... is False` to decide whether to auto-accept.
Under that reading NULL means "manually approve", while every other reader in
the codebase (`shared.user.follow_user`, the profile UI) treats NULL as
auto-accept. The result for a NULL row is that local follows are accepted
immediately but remote follows silently queue in /user/follow_requests, which
the user has no reason to visit -- their follower count just stops growing.

The code side is fixed (see SP-030); this backfill removes the ambiguity from
the data as well, so the question cannot come back via a future reader that
gets the NULL handling wrong again.

Scoped to local users (`ap_id IS NULL`) deliberately. For remote actors the
column mirrors `manuallyApprovesFollowers` from their actor JSON, and NULL
there means "we have not seen a value" -- writing False would be asserting
something about a remote user that we do not know.

Idempotent: re-running touches nothing once no NULLs remain.

Revision ID: 20260817_manual_approve_backfill
Revises: merge_20260817_v1711
Create Date: 2026-08-17

"""

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = "20260817_manual_approve_backfill"
down_revision = "merge_20260817_v1711"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE "user"
        SET ap_manually_approves_followers = false
        WHERE ap_id IS NULL
          AND ap_manually_approves_followers IS NULL
        """
    )


def downgrade():
    # Not reversible: the pre-migration NULLs are indistinguishable from rows
    # that legitimately hold False, so restoring them would be a guess. A
    # no-op downgrade is correct -- False is the column's documented default
    # and every reader treats NULL and False identically once SP-030 is in.
    pass
