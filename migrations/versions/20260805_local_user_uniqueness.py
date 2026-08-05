"""Add DB-level uniqueness for local usernames and emails

`User.user_name` and `User.email` carried plain indexes only, so uniqueness
rested entirely on a SELECT in the registration path
(`validate_user_availability()`) — a TOCTOU window: two concurrent registrations
can both find a name free and both insert it.

Scope: **local users only** (`ap_id IS NULL`). A global unique index would break
federation — two remote users named `alice` on different instances are entirely
legitimate and must coexist. Impersonation on *this* instance is what matters,
and that is exactly the local set.

Case-insensitive, matching how the application already reasons about names:
`validate_user_availability()` rejects case variants via `ilike`, and
`app/models.py` already carries a functional index on `lower(user_name)`.

Deleted users are deliberately included. Nothing renames `user_name` on
deletion, and `validate_user_availability()` does not exempt deleted rows, so
a deleted local username is already treated as taken. Email is different:
account deletion rewrites it to `deleted_<id>@deleted.com`
(`app/user/routes.py`), which is inherently unique, so deleted rows cannot
collide.

Empty and NULL emails are excluded — remote users have no email, and PostgreSQL
already permits unlimited NULLs in a unique index, but the empty string is a
real value that would collide.

Note `User.ap_profile_id` is already `unique=True`, and for local users it is
derived from the username (`https://<server>/u/<name>`). That closes part of the
same race, but only once `finalize_user_setup()` has run — it sets the column
after the row is inserted, so a concurrent pair can both insert with
`ap_profile_id IS NULL` (and NULLs don't conflict) and only collide later, at a
point where a half-created account already exists. These indexes make the
conflict happen at INSERT, where it belongs.

Revision ID: 20260805_local_user_uniq
Revises: merge_20260805_v1710
Create Date: 2026-08-05

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260805_local_user_uniq"
down_revision = "merge_20260805_v1710"
branch_labels = None
depends_on = None


USERNAME_INDEX = "uq_user_local_user_name_lower"
EMAIL_INDEX = "uq_user_local_email_lower"

_DUP_USERNAMES = sa.text("""
    SELECT lower(user_name) AS value, count(*) AS n
    FROM "user"
    WHERE ap_id IS NULL
    GROUP BY 1 HAVING count(*) > 1
    ORDER BY n DESC, value
    LIMIT 25
""")

_DUP_EMAILS = sa.text("""
    SELECT lower(email) AS value, count(*) AS n
    FROM "user"
    WHERE ap_id IS NULL AND email IS NOT NULL AND email <> ''
    GROUP BY 1 HAVING count(*) > 1
    ORDER BY n DESC, value
    LIMIT 25
""")


def _abort_on_duplicates(bind):
    """Fail with something actionable instead of an opaque index-build error.

    A unique index build against existing duplicates fails with
    `could not create unique index ... Key (lower(user_name))=(x) is duplicated`
    naming only the first offender, one run at a time. Report them all up front.
    """
    problems = []

    for label, query, column in (
        ("username", _DUP_USERNAMES, "user_name"),
        ("email", _DUP_EMAILS, "email"),
    ):
        rows = bind.execute(query).fetchall()
        if rows:
            listed = ", ".join(f"{r.value!r} x{r.n}" for r in rows)
            problems.append(
                f"  duplicate local {label}s ({len(rows)} shown): {listed}"
            )

    if problems:
        raise RuntimeError(
            "Cannot add local-user uniqueness constraints: existing rows already "
            "violate them.\n"
            + "\n".join(problems)
            + "\n\nResolve the duplicates first, then re-run this migration. "
            "Inspect them with:\n"
            '  SELECT id, user_name, email, created, deleted, banned FROM "user"\n'
            '  WHERE ap_id IS NULL AND lower(user_name) IN (...)\n'
            "  ORDER BY lower(user_name), id;\n"
            "Typically the oldest row is the real account. Do not delete rows "
            "blindly — they own posts, comments and votes."
        )


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Partial functional indexes are PostgreSQL-specific; SQLite test
        # databases are built with create_all() and never run migrations.
        return

    _abort_on_duplicates(bind)

    # Builds take an exclusive write lock on "user" for the duration. On a large
    # instance, create these CONCURRENTLY by hand outside the migration instead
    # (CONCURRENTLY cannot run inside a transaction, so Alembic cannot issue it
    # here), then stamp this revision.
    op.execute(
        sa.text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS {USERNAME_INDEX} '
            'ON "user" (lower(user_name)) WHERE ap_id IS NULL'
        )
    )
    op.execute(
        sa.text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS {EMAIL_INDEX} '
            'ON "user" (lower(email)) '
            "WHERE ap_id IS NULL AND email IS NOT NULL AND email <> ''"
        )
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP INDEX IF EXISTS {EMAIL_INDEX}"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS {USERNAME_INDEX}"))
