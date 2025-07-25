"""unique instance domain

Revision ID: d88b49617de0
Revises: c3cc707ab5e9
Create Date: 2024-11-24 16:22:16.733285

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'd88b49617de0'
down_revision = 'c3cc707ab5e9'
branch_labels = None
depends_on = None


def upgrade():
    # Find duplicate communities by ap_profile_id
    dupes_query = text('''
                SELECT domain FROM "instance" 
                GROUP BY domain 
                HAVING COUNT(*) > 1
            ''')

    conn = op.get_bind()
    duplicate_instances = conn.execute(dupes_query).scalars()
    print('Cleaning up duplicate instances...')

    for domain in duplicate_instances:
        if domain is None:
            continue
        # Get all communities with the same ap_profile_id, ordered by ID
        users_query = text('''
                    SELECT id FROM "instance" 
                    WHERE domain = :domain 
                    ORDER BY id
                ''')
        instances = conn.execute(users_query, {"domain": domain}).fetchall()

        # Set the lowest ID as the new_id, and collect other IDs to update/delete
        new_id = instances[0].id
        old_ids = [instance.id for instance in instances[1:]]

        print(domain)

        if old_ids:
            # Update tables with batch IN clause
            conn.execute(text('UPDATE "community" SET instance_id = :new_id WHERE instance_id IN :old_ids'), {"new_id": new_id, "old_ids": tuple(old_ids)})
            conn.execute(text('UPDATE "user" SET instance_id = :new_id WHERE instance_id IN :old_ids'), {"new_id": new_id, "old_ids": tuple(old_ids)})
            conn.execute(text('UPDATE "post" SET instance_id = :new_id WHERE instance_id IN :old_ids'), {"new_id": new_id, "old_ids": tuple(old_ids)})
            conn.execute(text('UPDATE "post_reply" SET instance_id = :new_id WHERE instance_id IN :old_ids'), {"new_id": new_id, "old_ids": tuple(old_ids)})
            conn.execute(text('UPDATE "report" SET source_instance_id = :new_id WHERE source_instance_id IN :old_ids'), {"new_id": new_id, "old_ids": tuple(old_ids)})
            conn.execute(text('DELETE FROM "instance_role" WHERE instance_id IN :old_ids'), {"old_ids": tuple(old_ids)})
            conn.execute(text('DELETE FROM "instance_block" WHERE instance_id IN :old_ids'), {"old_ids": tuple(old_ids)})

            # Delete the duplicate instances
            conn.execute(text('DELETE FROM "instance" WHERE id IN :old_ids'), {"old_ids": tuple(old_ids)})
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('instance', schema=None) as batch_op:
        batch_op.drop_index('ix_instance_domain')
        batch_op.create_index(batch_op.f('ix_instance_domain'), ['domain'], unique=True)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('instance', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_instance_domain'))
        batch_op.create_index('ix_instance_domain', ['domain'], unique=False)

    # ### end Alembic commands ###
