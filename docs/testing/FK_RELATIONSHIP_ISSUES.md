# Foreign Key Relationship Issues in PyFedi/PeachPie

## Overview

The PyFedi codebase is experiencing SQLAlchemy relationship configuration errors due to ambiguous foreign key paths between tables. When SQLAlchemy finds multiple foreign key paths between two tables, it cannot automatically determine which path to use for a relationship, requiring explicit configuration.

## Current Issues

### 1. User ↔ Community (PARTIALLY FIXED)

**Issue**: Multiple foreign key paths exist between User and Community tables.

**Foreign Keys in Community table**:
- `user_id` (creator of the community)
- `deleted_by` (user who deleted the community)

**Relationship**: `User.created_communities`

**Fix Applied**:
```python
# In app/models/user.py
created_communities = relationship('Community', foreign_keys='Community.user_id',
                                  back_populates='creator', lazy='dynamic')
```

### 2. User ↔ ModLog (NEEDS FIX)

**Issue**: Multiple foreign key paths between User and ModLog tables.

**Error Message**:
```
sqlalchemy.exc.AmbiguousForeignKeysError: Could not determine join condition between 
parent/child tables on relationship User.mod_actions - there are multiple foreign key 
paths linking the tables.
```

**Likely Foreign Keys in ModLog**:
- User who performed the action
- User who was the target of the action
- Possibly a third user reference

**Relationship**: `User.mod_actions`

### 3. User ↔ CommunityBan (FIXED)

**Issue**: Multiple user references in CommunityBan table.

**Foreign Keys in CommunityBan**:
- `user_id` (banned user)
- `banned_by_id` (moderator who issued the ban)

**Fix Applied**:
```python
# In app/models/user.py
community_bans = relationship('CommunityBan', foreign_keys='CommunityBan.user_id',
                             back_populates='user', lazy='dynamic',
                             cascade='all, delete-orphan')

# In app/models/community.py
user = relationship('User', foreign_keys=[user_id], back_populates='community_bans')
banned_by = relationship('User', foreign_keys=[banned_by_id])
```

### 4. ChatMessage ↔ Conversation (CIRCULAR DEPENDENCY)

**Issue**: Circular dependency when dropping tables, suggesting complex relationships.

**Error Message**:
```
sqlalchemy.exc.CircularDependencyError: Can't sort tables for DROP; an unresolvable 
foreign key dependency exists between tables: chat_message, conversation.
```

**Relationships**:
- Conversation has messages (one-to-many)
- ChatMessage belongs to a conversation
- Conversation has two user participants (user1_id, user2_id)

### 5. User ↔ Conversation

**Issue**: Multiple user references in Conversation table.

**Foreign Keys in Conversation**:
- `user1_id` (first participant)
- `user2_id` (second participant)

## Pattern of Issues

Most ambiguous foreign key issues follow this pattern:
1. A table references the User table multiple times for different purposes
2. SQLAlchemy cannot determine which foreign key to use for a relationship
3. The solution is to explicitly specify the `foreign_keys` parameter

## Common Tables with Multiple User References

Based on the errors and code analysis, these tables likely have multiple User foreign keys:

1. **ModLog**: actor, target user, possibly admin who reviewed
2. **Community**: creator, deleted_by
3. **CommunityBan**: banned user, banner
4. **Conversation**: two participants
5. **Report**: reporter, reported user, handler
6. **Post**: author, deleted_by
7. **PostReply**: author, deleted_by
8. **Notification**: recipient, actor

## Recommended Fixes

### General Pattern
```python
# When defining relationships with multiple FK paths, be explicit:
relationship_name = relationship('TargetModel', 
                               foreign_keys='TargetModel.specific_fk_column',
                               back_populates='reverse_relationship_name')
```

### For ModLog (example)
```python
# In User model
mod_actions_performed = relationship('ModLog', 
                                   foreign_keys='ModLog.actor_id',
                                   back_populates='actor')
mod_actions_received = relationship('ModLog', 
                                  foreign_keys='ModLog.target_user_id',
                                  back_populates='target_user')
```

### For Circular Dependencies
Consider:
1. Adding names to foreign key constraints for explicit dropping
2. Using `use_alter=True` on one of the foreign keys
3. Reviewing if the circular dependency is necessary

## Next Steps

1. **Audit all models** for multiple foreign keys to the same table
2. **Add explicit foreign_keys** parameters to all ambiguous relationships
3. **Name foreign key constraints** to help with circular dependencies
4. **Test each relationship** after fixing to ensure proper behavior
5. **Document the relationship structure** for future maintenance

## Model Files to Review

- `/app/models/user.py` - Central to most relationships
- `/app/models/moderation.py` - ModLog and Report models
- `/app/models/community.py` - Community-related models
- `/app/models/notification.py` - Conversation and ChatMessage
- `/app/models/content.py` - Post and PostReply

## Testing After Fixes

Once relationships are properly configured:
1. Application should start without SQLAlchemy errors
2. Database migrations should run cleanly
3. Tests should be able to create/query related objects
4. Cascade deletes should work as expected