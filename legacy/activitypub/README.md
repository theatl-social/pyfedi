# Legacy ActivityPub Files

This folder contains the original untyped versions of ActivityPub files that have been replaced with fully typed versions.

## Files Moved Here

### untyped_util.py (2025-01-27)
- **Original location**: app/activitypub/util.py
- **Replaced by**: app/activitypub/util.py (typed version)
- **Key improvements in typed version**:
  - Full type annotations for all functions
  - subprocess.run() instead of os.system() for security
  - Better error handling
  - Type-safe ActivityPub object definitions

### untyped_signature.py (2025-01-27)
- **Original location**: app/activitypub/signature.py  
- **Replaced by**: app/activitypub/signature.py (typed version)
- **Key improvements in typed version**:
  - Full type annotations
  - Better error handling
  - Type-safe signature verification

### untyped_find_object.py (2025-01-27)
- **Original location**: app/activitypub/find_object.py
- **Replaced by**: app/activitypub/find_object.py (typed version)
- **Key improvements in typed version**:
  - Full type annotations
  - Better object resolution logic
  - Type-safe returns

## Migration Notes

All functionality from these untyped files has been preserved in the typed versions.
The typed versions include:
- Python 3.13 type annotations
- Improved error handling
- Better security practices
- More maintainable code structure