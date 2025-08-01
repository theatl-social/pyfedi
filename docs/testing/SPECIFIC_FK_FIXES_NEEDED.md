# Specific Foreign Key Fixes Needed

**Generated**: 2025-08-01  
**Purpose**: Exact fixes needed to resolve SQLAlchemy relationship errors

## 🔴 Critical Fix #1: User.notifications

### Current Code (BROKEN)
```python
# In app/models/user.py:144
notifications = relationship('Notification', back_populates='user', lazy='dynamic',
                           cascade='all, delete-orphan')
```

### Problem
The Notification model has TWO foreign keys to User:
- `user_id` (line 36) - The recipient
- `author_id` (line 47) - The notification creator

SQLAlchemy can't determine which FK to use.

### Fix Required
```python
# In app/models/user.py:144
notifications = relationship('Notification', foreign_keys='Notification.user_id',
                           back_populates='user', lazy='dynamic',
                           cascade='all, delete-orphan')
```

## 🟡 Additional Issues Found

### 1. Community.deleted_by Missing Relationship
```python
# In app/models/community.py
# Has FK: deleted_by = mapped_column(Integer, ForeignKey('user.id'))
# But NO relationship defined!

# Add this:
deleted_by_user = relationship('User', foreign_keys=[deleted_by])
```

### 2. Single FK Relationships Missing foreign_keys (Best Practice)

While these won't cause immediate errors, they should specify foreign_keys for consistency:

```python
# In app/models/notification.py:171
sender = relationship('User')  # Should be:
sender = relationship('User', foreign_keys=[sender_id])

# In app/models/notification.py:95
user = relationship('NotificationSubscription', back_populates='user')  # Should be:
user = relationship('NotificationSubscription', foreign_keys=[user_id], back_populates='user')
```

## Quick Test Commands

After fixing User.notifications, run:
```bash
# Test if the fix works
docker-compose -f docker/test/docker-compose.yml down -v
docker-compose -f docker/test/docker-compose.yml up --build test-runner 2>&1 | grep -E "(passed|failed|error)" | tail -5

# Or run specific test
docker-compose -f docker/test/docker-compose.yml run --rm test-runner pytest tests/test_allowlist_html.py -xvs
```

## Summary of All Models with Multiple User FKs

✅ = Properly configured  
❌ = Needs fix

| Model | User FKs | Status |
|-------|----------|--------|
| Notification | user_id, author_id | ❌ User.notifications missing foreign_keys |
| Conversation | user1_id, user2_id | ✅ Both relationships properly configured |
| Report | reporter_id, suspect_user_id, resolved_by_id | ✅ All relationships properly configured |
| ModLog | user_id, target_user_id | ✅ Both relationships properly configured (we fixed this) |
| Community | user_id, deleted_by | ⚠️ deleted_by relationship missing |
| CommunityBan | user_id, banned_by_id | ✅ Both relationships properly configured |
| UserFollower | follower_id, followed_id | ✅ Both relationships properly configured |
| UserFollowRequest | follower_id, followed_id | ✅ Both relationships properly configured |
| UserBlock | blocker_id, blocked_id | ✅ Both relationships properly configured |
| UserNote | author_id, target_id | ✅ Both relationships properly configured |

## Start Here

1. **Fix User.notifications first** - This is blocking all tests
2. Run tests to see if other FK errors appear
3. Add Community.deleted_by_user relationship if needed
4. Consider adding foreign_keys to all single-FK relationships for consistency