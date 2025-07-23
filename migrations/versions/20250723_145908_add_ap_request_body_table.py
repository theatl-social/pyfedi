"""Add ap_request_body table for storing POST content

Revision ID: 20250723_145908
Revises: 
Create Date: 2025-01-23 14:59:08.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


# revision identifiers, used by Alembic.
revision = '20250723_145908'
down_revision = None  # Update this with the latest revision ID
branch_labels = None
depends_on = None


def upgrade():
    # Create ap_request_body table
    op.create_table('ap_request_body',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('headers', JSON(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('parsed_json', JSON(), nullable=True),
        sa.Column('content_type', sa.String(length=128), nullable=True),
        sa.Column('content_length', sa.Integer(), nullable=True),
        sa.Column('remote_addr', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_ap_request_body_request_id', 'ap_request_body', ['request_id'], unique=True)
    
    # Set default timestamp
    op.alter_column('ap_request_body', 'timestamp',
                    server_default=sa.text('now()'))


def downgrade():
    # Drop indexes first
    op.drop_index('ix_ap_request_body_request_id', table_name='ap_request_body')
    
    # Drop table
    op.drop_table('ap_request_body')
