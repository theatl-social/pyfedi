# Database Schema Improvement Recommendations

## Critical Issues to Fix

### 1. URL Field Lengths

**Problem**: Many URL fields are limited to 255-256 characters, which is insufficient for ActivityPub.

**Current Issues**:
```python
# Too short - URLs can be much longer
ap_inbox_url = db.Column(db.String(255))
ap_profile_id = db.Column(db.String(255))
ap_id = db.Column(db.String(255))
source_url = db.Column(db.String(1024))  # Still too short for some URLs
```

**Recommended Fix**:
```python
# Migration to increase URL field lengths
def upgrade():
    # Change all ActivityPub URL fields to TEXT (unlimited)
    op.alter_column('user', 'ap_profile_id', type_=sa.Text())
    op.alter_column('user', 'ap_inbox_url', type_=sa.Text())
    op.alter_column('user', 'ap_public_url', type_=sa.Text())
    op.alter_column('community', 'ap_profile_id', type_=sa.Text())
    op.alter_column('community', 'ap_inbox_url', type_=sa.Text())
    op.alter_column('post', 'ap_id', type_=sa.Text())
    op.alter_column('file', 'source_url', type_=sa.Text())
    # ... etc for all URL fields
```

### 2. Email Field Length

**Problem**: Email fields are 255 chars but valid emails can be up to 320 chars.

**Fix**:
```python
email = db.Column(db.String(320), index=True)
```

### 3. Missing Indexes

**Problem**: Missing indexes for common query patterns.

**Add these indexes**:
```python
# Composite indexes for common queries
__table_args__ = (
    # For finding active users by instance
    db.Index('idx_user_instance_active', 'instance_id', 'deleted', 'banned'),
    
    # For post queries by community and time
    db.Index('idx_post_community_created', 'community_id', 'created_at', 'deleted'),
    
    # For activity log queries
    db.Index('idx_activitypublog_result_timestamp', 'result', 'timestamp'),
    
    # For federation error tracking
    db.Index('idx_federationerror_instance_created', 'instance_id', 'created_at'),
)
```

### 4. Data Type Improvements

**IP Address Storage**:
```python
# Current
ip_address = db.Column(db.String(50))

# Better (PostgreSQL)
from sqlalchemy.dialects.postgresql import INET
ip_address = db.Column(INET)
```

**JSON Fields**:
```python
# Current
activity_json = db.Column(db.JSON)

# Better (PostgreSQL)
from sqlalchemy.dialects.postgresql import JSONB
activity_json = db.Column(JSONB)  # Better indexing and operators
```

**Timestamps**:
```python
# Current
created_at = db.Column(db.DateTime, default=utcnow)

# Better
created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
```

### 5. Add Constraints

**Check Constraints**:
```python
__table_args__ = (
    # Email validation
    db.CheckConstraint("email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'", 
                       name='valid_email'),
    
    # Status validation
    db.CheckConstraint("status IN ('draft', 'published', 'scheduled', 'deleted')", 
                       name='valid_post_status'),
    
    # Score validation
    db.CheckConstraint('score >= 0', name='positive_score'),
)
```

**Foreign Key Constraints**:
```python
# Add ON DELETE CASCADE where appropriate
user_id = db.Column(db.Integer, 
                    db.ForeignKey('user.id', ondelete='CASCADE'), 
                    nullable=False)
```

## Migration Script Template

```python
"""Improve database schema

Revision ID: xxx
Revises: yyy
Create Date: 2025-01-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # 1. Fix URL field lengths
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('ap_profile_id', type_=sa.Text())
        batch_op.alter_column('ap_inbox_url', type_=sa.Text())
        batch_op.alter_column('ap_public_url', type_=sa.Text())
        batch_op.alter_column('email', type_=sa.String(320))
    
    # 2. Add missing indexes
    op.create_index('idx_user_instance_active', 'user', 
                    ['instance_id', 'deleted', 'banned'])
    op.create_index('idx_post_community_created', 'post', 
                    ['community_id', 'created_at', 'deleted'])
    
    # 3. Add check constraints
    op.create_check_constraint('valid_email', 'user',
        "email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'")
    
    # 4. Convert to better data types (PostgreSQL specific)
    if op.get_bind().dialect.name == 'postgresql':
        # Convert JSON to JSONB
        op.alter_column('activitypub_log', 'activity_json',
                       type_=postgresql.JSONB,
                       postgresql_using='activity_json::jsonb')
        
        # Convert IP addresses to INET
        op.alter_column('instance', 'ip_address',
                       type_=postgresql.INET,
                       postgresql_using='ip_address::inet')

def downgrade():
    # Reverse the changes
    pass
```

## Performance Considerations

### 1. Partial Indexes
For soft-deleted records:
```python
db.Index('idx_post_active', 'community_id', 'created_at', 
         postgresql_where='deleted = false')
```

### 2. GiST Indexes for Full-Text Search
```python
db.Index('idx_post_search', 'title', 'body',
         postgresql_using='gin',
         postgresql_ops={
             'title': 'gin_trgm_ops',
             'body': 'gin_trgm_ops'
         })
```

### 3. Covering Indexes
```python
db.Index('idx_user_lookup', 'user_name', 'instance_id',
         postgresql_include=['email', 'banned', 'deleted'])
```

## Implementation Priority

1. **Immediate** (Breaking Issues):
   - Fix URL field lengths
   - Fix email field length
   - Add missing foreign key indexes

2. **Soon** (Performance):
   - Add composite indexes
   - Add partial indexes for soft deletes
   - Convert to JSONB for better querying

3. **Future** (Optimization):
   - Add check constraints
   - Convert to native PostgreSQL types
   - Add covering indexes

## Testing the Changes

1. Backup database before migration
2. Test migration on development database
3. Verify all queries still work
4. Check query performance improvements
5. Test with real ActivityPub data (long URLs)