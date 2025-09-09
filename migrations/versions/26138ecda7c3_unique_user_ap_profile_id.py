"""unique user ap profile id

Revision ID: 26138ecda7c3
Revises: a4debcf5ac6f
Create Date: 2024-11-14 19:28:59.596757

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "26138ecda7c3"
down_revision = "a4debcf5ac6f"
branch_labels = None
depends_on = None


def upgrade():
    # Find duplicate users by ap_profile_id
    dupes_query = text(
        """
        SELECT ap_profile_id FROM "user" 
        GROUP BY ap_profile_id 
        HAVING COUNT(*) > 1
    """
    )

    conn = op.get_bind()
    duplicate_profiles = conn.execute(dupes_query).scalars()
    print("Cleaning up duplicate users, this may take a while...")

    for profile_id in duplicate_profiles:
        if profile_id is None:
            continue
        # Get all users with the same ap_profile_id, ordered by ID
        users_query = text(
            """
            SELECT id FROM "user" 
            WHERE ap_profile_id = :ap_profile_id 
            ORDER BY id
        """
        )
        users = conn.execute(users_query, {"ap_profile_id": profile_id}).fetchall()

        # Set the lowest ID as the new_id, and collect other IDs to update/delete
        new_id = users[0].id
        old_ids = [user.id for user in users[1:]]

        print(profile_id)

        if old_ids:
            # Update tables with batch IN clause
            conn.execute(
                text('UPDATE "post" SET user_id = :new_id WHERE user_id IN :old_ids'),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "post_vote" WHERE user_id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "post_vote" WHERE author_id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "post_reply" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "post_reply_vote" WHERE user_id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "post_reply_vote" WHERE author_id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "notification" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "notification" SET author_id = :new_id WHERE author_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "notification_subscription" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "community_member" WHERE user_id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "instance_role" WHERE user_id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "mod_log" WHERE user_id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "chat_message" SET sender_id = :new_id WHERE sender_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "conversation" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "chat_message" SET recipient_id = :new_id WHERE recipient_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "conversation_member" WHERE user_id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "community" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "domain_block" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "community_block" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "user_follower" WHERE local_user_id IN :old_ids'),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('DELETE FROM "user_follower" WHERE remote_user_id IN :old_ids'),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "community_ban" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "user_note" SET target_id = :new_id WHERE target_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "user_block" SET blocked_id = :new_id WHERE blocked_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "community_join_request" SET user_id = :new_id WHERE user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text('UPDATE "filter" SET user_id = :new_id WHERE user_id IN :old_ids'),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "report" SET reporter_id = :new_id WHERE reporter_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "report" SET suspect_user_id = :new_id WHERE suspect_user_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )
            conn.execute(
                text(
                    'UPDATE "user_follow_request" SET follow_id = :new_id WHERE follow_id IN :old_ids'
                ),
                {"new_id": new_id, "old_ids": tuple(old_ids)},
            )

            # Delete the duplicate users
            conn.execute(
                text('DELETE FROM "user" WHERE id IN :old_ids'),
                {"old_ids": tuple(old_ids)},
            )

    # Finalize by dropping and recreating the unique index on ap_profile_id
    with op.batch_alter_table("user", schema=None) as batch_op:
        print("Adding unique index...")
        batch_op.drop_index("ix_user_ap_profile_id")
        batch_op.create_index(
            batch_op.f("ix_user_ap_profile_id"), ["ap_profile_id"], unique=True
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_ap_profile_id"))
        batch_op.create_index("ix_user_ap_profile_id", ["ap_profile_id"], unique=False)

    # ### end Alembic commands ###
