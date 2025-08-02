"""Fix boolean columns that are incorrectly stored as integers

Revision ID: 20250802230000
Revises: 20250802174200
Create Date: 2025-08-02 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250802230000'
down_revision = '20250802174200'
branch_labels = None
depends_on = None


def upgrade():
    # Fix User table boolean columns
    # ignore_bots: int -> boolean
    op.execute("UPDATE \"user\" SET ignore_bots = CASE WHEN ignore_bots = 0 THEN 0 ELSE 1 END")
    op.alter_column('user', 'ignore_bots',
                    type_=sa.Boolean(),
                    existing_type=sa.Integer(),
                    postgresql_using='ignore_bots::boolean',
                    nullable=False,
                    server_default='false')
    
    # hide_nsfw: int -> boolean
    op.execute("UPDATE \"user\" SET hide_nsfw = CASE WHEN hide_nsfw = 0 THEN 0 ELSE 1 END")
    op.alter_column('user', 'hide_nsfw',
                    type_=sa.Boolean(),
                    existing_type=sa.Integer(),
                    postgresql_using='hide_nsfw::boolean',
                    nullable=False,
                    server_default='false')
    
    # hide_nsfl: int -> boolean
    op.execute("UPDATE \"user\" SET hide_nsfl = CASE WHEN hide_nsfl = 0 THEN 0 ELSE 1 END")
    op.alter_column('user', 'hide_nsfl',
                    type_=sa.Boolean(),
                    existing_type=sa.Integer(),
                    postgresql_using='hide_nsfl::boolean',
                    nullable=False,
                    server_default='false')
    
    # ban_state: int -> boolean (renamed to is_banned for clarity)
    # First drop the default
    op.alter_column('user', 'ban_state', server_default=None)
    # Update values
    op.execute("UPDATE \"user\" SET ban_state = CASE WHEN ban_state = 0 THEN 0 ELSE 1 END")
    # Change type and rename
    op.alter_column('user', 'ban_state',
                    new_column_name='is_banned',
                    type_=sa.Boolean(),
                    existing_type=sa.Integer(),
                    postgresql_using='ban_state::boolean',
                    nullable=False)
    # Add new default
    op.alter_column('user', 'is_banned', server_default='false')


def downgrade():
    # Revert User table boolean columns back to integers
    op.alter_column('user', 'is_banned',
                    new_column_name='ban_state',
                    type_=sa.Integer(),
                    existing_type=sa.Boolean(),
                    postgresql_using='is_banned::integer',
                    nullable=False,
                    server_default='0')
    
    op.alter_column('user', 'hide_nsfl',
                    type_=sa.Integer(),
                    existing_type=sa.Boolean(),
                    postgresql_using='hide_nsfl::integer',
                    nullable=False,
                    server_default='0')
    
    op.alter_column('user', 'hide_nsfw',
                    type_=sa.Integer(),
                    existing_type=sa.Boolean(),
                    postgresql_using='hide_nsfw::integer',
                    nullable=False,
                    server_default='0')
    
    op.alter_column('user', 'ignore_bots',
                    type_=sa.Integer(),
                    existing_type=sa.Boolean(),
                    postgresql_using='ignore_bots::integer',
                    nullable=False,
                    server_default='0')