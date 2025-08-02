"""Fix circular foreign key constraints between conversation and chat_message

Revision ID: fix_circular_fk_constraints
Revises: add_language_native_name
Create Date: 2025-08-02 17:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_circular_fk_constraints'
down_revision = 'add_language_native_name'
branch_labels = None
depends_on = None


def upgrade():
    # Drop existing unnamed constraints and recreate with names
    # This helps avoid circular dependency issues during table drops
    
    # PostgreSQL-specific approach - check constraint names first
    with op.get_bind() as conn:
        # Get existing constraint names
        result = conn.execute(sa.text("""
            SELECT conname 
            FROM pg_constraint 
            WHERE conrelid = 'conversation'::regclass 
            AND confrelid = 'chat_message'::regclass
            AND contype = 'f'
        """))
        old_constraint = result.scalar()
        
        if old_constraint:
            op.drop_constraint(old_constraint, 'conversation', type_='foreignkey')
        
        # Add named constraint for conversation.last_message_id
        op.create_foreign_key(
            'fk_conversation_last_message_id',
            'conversation', 'chat_message',
            ['last_message_id'], ['id']
        )
        
        # Get constraint for chat_message.conversation_id
        result = conn.execute(sa.text("""
            SELECT conname 
            FROM pg_constraint 
            WHERE conrelid = 'chat_message'::regclass 
            AND confrelid = 'conversation'::regclass
            AND contype = 'f'
        """))
        old_constraint = result.scalar()
        
        if old_constraint:
            op.drop_constraint(old_constraint, 'chat_message', type_='foreignkey')
        
        # Add named constraint for chat_message.conversation_id
        op.create_foreign_key(
            'fk_chat_message_conversation_id',
            'chat_message', 'conversation',
            ['conversation_id'], ['id']
        )


def downgrade():
    # Revert to unnamed constraints
    op.drop_constraint('fk_conversation_last_message_id', 'conversation', type_='foreignkey')
    op.create_foreign_key(None, 'conversation', 'chat_message', ['last_message_id'], ['id'])
    
    op.drop_constraint('fk_chat_message_conversation_id', 'chat_message', type_='foreignkey')
    op.create_foreign_key(None, 'chat_message', 'conversation', ['conversation_id'], ['id'])