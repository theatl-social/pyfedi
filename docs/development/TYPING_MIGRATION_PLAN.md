# Type Migration Plan

## Current Situation

We have several "typed_" Python files that are not simple duplicates but improved versions:
- `app/activitypub/typed_util.py` - Has type annotations + uses subprocess instead of os.system
- `app/activitypub/typed_signature.py` - Has type annotations + improved implementations
- `app/activitypub/typed_find_object.py` - Typed version of object finding logic
- `app/models_typed_relations.py` - DUPLICATE - already in new model structure

## Migration Strategy

### 1. Remove Clear Duplicates
- [x] models_typed_relations.py - Already covered in app/models/

### 2. Merge Typed Versions Into Main Files
For each typed_ file:
1. Compare implementations
2. Take the better implementation (usually from typed_)
3. Ensure all type annotations are preserved
4. Remove the typed_ version

### 3. Add Type Annotations to Remaining Files
Priority order based on usage:
1. Core utilities (app/utils.py - 91/205 typed)
2. ActivityPub core (app/activitypub/util.py - 17/71 typed)
3. Security modules
4. API endpoints
5. Forms and UI helpers

## Files Needing Type Annotations (Top Priority)

1. **app/utils.py** - Core utilities, only 44% typed
2. **app/activitypub/util.py** - ActivityPub utilities, only 24% typed
3. **app/activitypub/signature.py** - Critical for federation, 39% typed
4. **app/auth/util.py** - Authentication, only 5% typed
5. **app/community/util.py** - Community functions, 36% typed

## Implementation Notes

- Use Python 3.13 type syntax
- Add `from __future__ import annotations` to all files
- Use `Optional[T]` for nullable values
- Use `Union[A, B]` or `A | B` for multiple types
- Add return type annotations to ALL functions
- Use `-> None` for functions that don't return values