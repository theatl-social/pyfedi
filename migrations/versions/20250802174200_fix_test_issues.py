"""Fix test issues: add language native_name and fix circular FK constraints

Revision ID: fix_test_issues
Revises: feef49234599
Create Date: 2025-08-02 17:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250802174200'
down_revision = '20250801193400'
branch_labels = None
depends_on = None


def upgrade():
    # Add native_name column to language table
    op.add_column('language', sa.Column('native_name', sa.String(length=50), nullable=True))
    
    # Add active column to language table
    op.add_column('language', sa.Column('active', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add weight column to role table if it doesn't exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('role')]
    if 'weight' not in columns:
        op.add_column('role', sa.Column('weight', sa.Integer(), nullable=False, server_default='0'))
    
    # Add role_id column to user table if it doesn't exist
    user_columns = [c['name'] for c in inspector.get_columns('user')]
    if 'role_id' not in user_columns:
        op.add_column('user', sa.Column('role_id', sa.Integer(), sa.ForeignKey('role.id'), nullable=True))
    
    # Add deleted and ban_state columns to user table if they don't exist
    if 'deleted' not in user_columns:
        op.add_column('user', sa.Column('deleted', sa.Boolean(), nullable=False, server_default='false'))
        op.create_index('ix_user_deleted', 'user', ['deleted'])
    if 'ban_state' not in user_columns:
        op.add_column('user', sa.Column('ban_state', sa.Integer(), nullable=False, server_default='0'))
    
    # Fix circular dependency between conversation and chat_message tables
    # by adding named constraints
    
    # PostgreSQL-specific approach - check constraint names first
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # Handle conversation.last_message_id constraint
    if bind.dialect.name == 'postgresql':
        # Check if tables exist before trying to modify constraints
        tables_exist = bind.execute(sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'conversation'
            ) AND EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'chat_message'
            )
        """)).scalar()
        
        if tables_exist:
            # Get existing constraint names
            result = bind.execute(sa.text("""
                SELECT conname 
                FROM pg_constraint 
                WHERE conrelid = 'conversation'::regclass 
                AND confrelid = 'chat_message'::regclass
                AND contype = 'f'
            """))
            old_constraint = result.scalar()
            
            if old_constraint and old_constraint != 'fk_conversation_last_message_id':
                op.drop_constraint(old_constraint, 'conversation', type_='foreignkey')
                op.create_foreign_key(
                    'fk_conversation_last_message_id',
                    'conversation', 'chat_message',
                    ['last_message_id'], ['id']
                )
        
        # Handle chat_message.conversation_id constraint
        result = bind.execute(sa.text("""
            SELECT conname 
            FROM pg_constraint 
            WHERE conrelid = 'chat_message'::regclass 
            AND confrelid = 'conversation'::regclass
            AND contype = 'f'
            AND conkey = ARRAY[2]::smallint[]
        """))
        old_constraint = result.scalar()
        
        if old_constraint and old_constraint != 'fk_chat_message_conversation_id':
            op.drop_constraint(old_constraint, 'chat_message', type_='foreignkey')
            op.create_foreign_key(
                'fk_chat_message_conversation_id',
                'chat_message', 'conversation',
                ['conversation_id'], ['id']
            )


def downgrade():
    # Remove columns from language table
    op.drop_column('language', 'active')
    op.drop_column('language', 'native_name')
    
    # Remove weight column from role table
    op.drop_column('role', 'weight')
    
    # Remove role_id column from user table
    op.drop_column('user', 'role_id')
    
    # Remove deleted and ban_state columns from user table
    op.drop_index('ix_user_deleted', 'user')
    op.drop_column('user', 'deleted')
    op.drop_column('user', 'ban_state')
    
    # Revert to unnamed constraints
    op.drop_constraint('fk_conversation_last_message_id', 'conversation', type_='foreignkey')
    op.create_foreign_key(None, 'conversation', 'chat_message', ['last_message_id'], ['id'])
    
    op.drop_constraint('fk_chat_message_conversation_id', 'chat_message', type_='foreignkey')
    op.create_foreign_key(None, 'chat_message', 'conversation', ['conversation_id'], ['id'])