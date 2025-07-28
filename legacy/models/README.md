# Legacy Models

This directory contains the original model files before consolidation and typing.

## Files

- **models_original.py** - The original untyped models.py file (2000+ lines)
- **models_typed.py** - Partially typed versions of core models (User, Community, Post, etc.)
- **models_typed_activitypub.py** - Typed versions of ActivityPub-specific models

## Why These Were Replaced

1. **Duplication** - Multiple files defined the same database tables causing SQLAlchemy conflicts
2. **Lack of Type Safety** - Original models had no type annotations
3. **Inconsistency** - Some models were typed, others weren't
4. **Maintenance Burden** - Having to maintain multiple versions of the same models

## What Replaced Them

All models have been consolidated into a fully-typed models structure:
- `app/models/` - Main models package with logical separation
  - `__init__.py` - Exports all models
  - `user.py` - User-related models
  - `community.py` - Community-related models
  - `content.py` - Post, PostReply, and other content models
  - `activitypub.py` - ActivityPub and federation models
  - `moderation.py` - Moderation and reporting models
  - `instance.py` - Instance and federation models
  - `base.py` - Base classes and mixins

All models now use:
- Full type annotations with Python 3.13 features
- SQLAlchemy 2.0 mapped_column syntax
- Proper relationships with type hints
- Consistent naming and structure