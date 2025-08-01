# Legacy Coding Tools

This directory contains utility scripts that were used during refactoring and migration processes.

## Scripts

### fix_utcnow_imports.py
- **Purpose**: Fixed circular import issues by updating files to import `utcnow` from `app.utils` instead of `app.models`
- **Date**: 2025-01-27
- **Status**: Successfully fixed 17 files
- **Context**: Part of the model consolidation refactoring to break circular dependencies