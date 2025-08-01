# PeachPie Rebranding Plan

## Overview

This document outlines the plan to rebrand PyFedi to PeachPie while maintaining full compatibility with the PyFedi federation protocol. The goal is to establish PeachPie as a distinct project while ensuring seamless interoperability with existing PyFedi instances.

## Principles

1. **Federation Compatibility**: PeachPie will remain 100% compatible with PyFedi instances
2. **Gradual Transition**: Changes will be made incrementally to avoid breaking existing deployments
3. **Clear Documentation**: All changes will be documented for operators and developers
4. **Backwards Compatibility**: Existing PyFedi configurations will continue to work

## Phase 1: Software Identity (Completed ✅)

### Environment Variables
- ✅ `SOFTWARE_NAME=PeachPie` (defaults to PeachPie, can be overridden)
- ✅ `SOFTWARE_REPO=https://github.com/theatl-social/peachpie`
- ✅ `SOFTWARE_VERSION` (configurable)

### User-Agent String
- ✅ Updated to use configurable SOFTWARE_NAME
- ✅ Format: `PeachPie/1.0.1 (+https://github.com/theatl-social/peachpie)`

### NodeInfo
- ✅ Reports software name from configuration
- ✅ Maintains protocol compatibility

## Phase 2: Codebase Updates (To Do)

### 1. Python Package Name
- Keep module name as `app` (no change needed)
- Update `setup.py` to use name="peachpie"
- PyPI package: `peachpie` (when published)

### 2. Docker Images
- Repository: `ghcr.io/theatl-social/peachpie`
- Tags: `latest`, `v1.0.0`, etc.
- Keep Dockerfile names unchanged

### 3. Configuration Files
- Rename example files:
  - `.env.example` → Already updated with PeachPie branding ✅
  - `docker-compose.yml` → Update service names and image references

### 4. Database Names
- Default database: `peachpie` (was `pyfedi`)
- Migration script already created ✅
- Tables remain unchanged (compatibility)

### 5. Redis Keys
- Keep existing key structure (no changes needed)
- Prefix remains generic (stream:, health:, etc.)

### 6. File Headers and Comments
- Update copyright notices
- Update file headers to reference PeachPie
- Keep historical PyFedi attribution

## Phase 3: Documentation Updates

### 1. README.md
- New header: "# PeachPie"
- Add "Fork of PyFedi" attribution
- Update all references
- Keep federation protocol docs unchanged

### 2. Documentation Files
- Update all .md files in /docs
- Change PyFedi → PeachPie in text
- Keep technical specifications unchanged

### 3. Code Comments
- Update inline documentation
- Change "PyFedi" references to "PeachPie"
- Preserve technical comments

### 4. API Documentation
- Update OpenAPI/Swagger descriptions
- Change server info to PeachPie
- Keep endpoint specifications unchanged

## Phase 4: Repository Changes

### 1. GitHub Repository
- Already at: https://github.com/theatl-social/peachpie
- Update repository description
- Add topics: activitypub, federation, python, redis

### 2. Issue Templates
- Update templates to reference PeachPie
- Keep issue categories unchanged

### 3. GitHub Actions
- Update workflow names
- Change artifact names to peachpie-*
- Keep workflow logic unchanged

## Phase 5: Deployment Updates

### 1. Systemd Service Files
- Rename to `peachpie.service`
- Update description and documentation

### 2. Nginx Configuration
- No changes needed (uses SERVER_NAME)

### 3. Deployment Scripts
- Update script names and references
- Keep functionality unchanged

## Phase 6: Community Communication

### 1. Announcement
- Blog post explaining the rebrand
- Emphasize continued PyFedi compatibility
- Highlight new features and improvements

### 2. Migration Guide
- Step-by-step upgrade instructions
- Configuration migration tool
- FAQ section

### 3. Federation Partners
- No action needed (protocol unchanged)
- NodeInfo will automatically report new name

## Implementation Checklist

### Immediate Changes
- [ ] Update README.md header and description
- [ ] Update setup.py with PeachPie package name
- [ ] Update docker-compose.yml service names
- [ ] Update all documentation files
- [ ] Update copyright headers in Python files

### Configuration Changes
- [ ] Update systemd service files
- [ ] Update deployment documentation
- [ ] Create Docker Hub / GHCR repositories

### Code Changes
- [ ] Update inline comments and docstrings
- [ ] Update error messages mentioning PyFedi
- [ ] Update admin interface branding
- [ ] Update email templates

### Testing
- [ ] Verify federation still works
- [ ] Test upgrade from PyFedi instance
- [ ] Verify all environment variables work
- [ ] Test Docker builds and deployment

## Backwards Compatibility

### Supported Forever
- PyFedi federation protocol
- Database schema
- API endpoints
- ActivityPub implementation

### Deprecated (but supported)
- PyFedi environment variable names (mapped to new ones)
- Old Docker image names (via tags)
- Legacy configuration files

### Migration Tools
- Automatic config migration script
- Database migration (already created)
- Environment variable mapping

## Timeline

1. **Week 1**: Documentation and README updates
2. **Week 2**: Code comments and strings
3. **Week 3**: Docker and deployment updates
4. **Week 4**: Testing and verification
5. **Week 5**: Release and announcement

## Success Criteria

- ✅ All PeachPie instances can federate with PyFedi instances
- ✅ Existing PyFedi deployments can upgrade seamlessly
- ✅ No breaking changes to federation protocol
- ✅ Clear documentation for operators
- ✅ Positive community reception

## Notes

- The protocol remains "PyFedi-compatible" for federation
- The software is "PeachPie" for branding
- Think of it like Mastodon/Pleroma - different software, same protocol
- PeachPie adds new features while maintaining compatibility