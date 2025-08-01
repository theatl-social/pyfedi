# Model-Database Schema Alignment Guide

This document captures the specific patterns and understanding gained from aligning PyFedi's models with the actual database schema.

## The Problem

PyFedi underwent a major refactoring where a 3390-line `models.py` file was split into typed, modular files. During this process:
1. New features were speculatively added to models
2. Column names were "improved" but no longer matched the database
3. Some existing columns were missed
4. The database schema (defined by migrations) became out of sync with models

## Key Understanding: Source of Truth

**The database schema is the source of truth**, not the model definitions. This is because:
- PyFedi is a running production system
- Existing data must be preserved
- The migrations define what actually exists in the database
- The original `models.py` (now in `/legacy/models/`) shows the working state

## Common Patterns Found

### 1. Speculative Features Added
Models included features that were never implemented:
- `User.avatar_nsfw`, `User.cover_nsfw` - NSFW flags for profile images
- `User.reply_notifications` - notification preference
- `User.email_visible` - profile visibility setting
- `User.birthday` - user birthday field

**Resolution**: Remove from models (no code uses them)

### 2. Column Name "Improvements"
Models used "better" names that didn't match the database:
- `hide_read_content` → should be `hide_read_posts`
- `reply_count` → should be `post_reply_count`
- `registered_at` → should be `created`
- `registration_open` → should be `registration_mode`

**Resolution**: Use original column names to match database

### 3. Missing Important Features
Some columns in models are used by code but missing from database:
- `User.suspended` - Used extensively for permission checks
- `User.totp_*` fields - Two-factor authentication

**Resolution**: Create migrations to add these useful features

### 4. Type/Default Mismatches
Models had different types or defaults than database:
- `registration_mode` default: 'open' (model) vs 'Closed' (database)
- `hide_nsfw`: Boolean (model) vs Integer (database)
- `attitude`: Float with default 0.0 (model) vs nullable Float (database)

**Resolution**: Match database types and defaults exactly

## Decision Framework

When you encounter a model-database mismatch:

```
Is the column used in application code?
├─ YES: Is it a useful feature?
│   ├─ YES: Create a migration to add it
│   └─ NO: Refactor code to remove usage
└─ NO: Does it exist in the database?
    ├─ YES: Fix model to match database
    └─ NO: Remove from model
```

## Specific Fixes Applied

### Site Model
- Removed: `require_application`, `enable_federation`, `terms`, `privacy_policy`
- Added: `gif_reply_filters`, `logo_*` fields, `blocked_phrases`, etc.
- Fixed: `updated_at` → `updated` (no TimestampMixin)

### User Model  
- Removed: `avatar_nsfw`, `cover_nsfw`, `reply_notifications`, `email_visible`, `birthday`
- Renamed: `hide_read_content` → `hide_read_posts`
- Renamed: `reply_count` → `post_reply_count`
- Renamed: `registered_at` → `created`
- Added migrations for: `suspended`, `totp_secret`, `totp_enabled`, `totp_recovery_codes`

### Instance Model
- Removed: `trust_level`, `online`, `last_failed_contact`
- Renamed: `last_successful_contact` → `last_successful_send`
- Added: `online()` method to replace removed column

## Validation Process

1. **Compare model with original**:
   ```python
   # Check legacy/models/models_original.py for the actual schema
   ```

2. **Check for migrations**:
   ```bash
   grep -r "column_name" migrations/
   ```

3. **Check code usage**:
   ```bash
   grep -r "\.column_name" app/
   ```

4. **Verify in database** (if available):
   ```sql
   \d table_name
   ```

## Lessons for Future Refactoring

1. **Never add speculative features during refactoring** - Refactoring should preserve behavior
2. **Keep original column names** - Even if they're not ideal
3. **Add features in separate commits** - Don't mix refactoring with new features
4. **Validate against database** - Models must match the actual schema
5. **Check code usage** - Ensure renamed fields are updated everywhere

## Migration Best Practices

When adding new columns:

1. **Always allow NULL initially** - Existing rows need a value
2. **Set defaults for existing rows** - Use SQL UPDATE
3. **Then make NOT NULL** - After defaults are set
4. **Index thoughtfully** - Add indexes for columns used in queries
5. **Test rollback** - Ensure downgrade() works

## Current State

After alignment:
- Site model: ✅ Fully aligned
- User model: ✅ Aligned with migrations added
- Instance model: ✅ Aligned
- Other models: 🔄 To be validated as errors appear

This systematic approach has resolved the majority of "column does not exist" errors and established a pattern for fixing the remaining ones.