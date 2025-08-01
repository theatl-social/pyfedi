# PeachPie Migration Plan

## Overview
Rename the project from PyFedi to PeachPie while maintaining full compatibility with PyFedi instances. From an external PyFedi server's perspective, PeachPie will appear as another PyFedi instance.

## Key Principles

### 1. Protocol Compatibility
- **ActivityPub**: No changes to ActivityPub implementation
- **Software Identification**: Continue reporting as "pyfedi" in NodeInfo for compatibility
- **API Endpoints**: Maintain all PyFedi-specific endpoints
- **Federation**: Full interoperability with existing PyFedi instances

### 2. Branding Strategy
- **Internal**: Use "PeachPie" in documentation, UI, and internal code
- **External**: Report as "pyfedi" in federation protocols for compatibility
- **Version**: Use PeachPie version scheme while maintaining PyFedi compatibility markers

## Implementation Areas

### 1. User-Facing Changes
- [ ] Update UI branding from PyFedi to PeachPie
- [ ] Change page titles and headers
- [ ] Update logos and icons
- [ ] Modify footer text
- [ ] Update about pages

### 2. Documentation Updates
- [ ] README.md - Main project documentation
- [ ] CONTRIBUTING.md - Contributor guidelines
- [ ] Installation guides
- [ ] API documentation
- [ ] Federation documentation
- [ ] All inline code comments mentioning PyFedi

### 3. Code Updates
- [ ] Update package metadata (setup.py, pyproject.toml)
- [ ] Change internal project references
- [ ] Update configuration examples
- [ ] Modify Docker image names
- [ ] Update environment variable prefixes (keep PYFEDI_ for compatibility)

### 4. Compatibility Layer
```python
# In nodeinfo.py
def get_software_info():
    return {
        "name": "pyfedi",  # Keep for compatibility
        "version": PEACHPIE_VERSION,
        "repository": "https://github.com/yourusername/peachpie",
        "homepage": "https://peachpie.social"
    }

# Add custom extension
def get_software_info_extended():
    return {
        "name": "peachpie",
        "pyfedi_compatible": True,
        "version": PEACHPIE_VERSION,
        "features": ["redis_streams", "enhanced_typing", "advanced_retry"]
    }
```

### 5. Feature Differentiation
PeachPie will maintain all PyFedi features plus:
- Redis Streams (replacing Celery)
- Enhanced type safety with Python 3.13
- Advanced retry mechanisms
- Improved monitoring capabilities
- Better performance optimizations

### 6. Migration Steps

#### Phase 1: Internal Branding
1. Update documentation files
2. Change UI elements
3. Modify internal references

#### Phase 2: External Identity
1. Set up PeachPie repository
2. Create PeachPie website/docs
3. Register peachpie.social domain

#### Phase 3: Compatibility Maintenance
1. Keep federation protocol unchanged
2. Maintain PyFedi API compatibility
3. Support PyFedi configuration formats

## File Changes Checklist

### Documentation Files
- [ ] README.md
- [ ] CONTRIBUTING.md
- [ ] INSTALL.md
- [ ] REFACTORING_PLAN.md
- [ ] REFACTORING_COMPLETE.md
- [ ] All README.md files in subdirectories

### Configuration Files
- [ ] .env.example
- [ ] docker-compose.yml
- [ ] Dockerfile
- [ ] pyproject.toml
- [ ] setup.py

### Code Files
- [ ] app/__init__.py (app name references)
- [ ] app/cli.py (CLI branding)
- [ ] app/templates/base.html (UI branding)
- [ ] app/templates/about.html
- [ ] app/templates/footer.html

### Keep Unchanged for Compatibility
- [ ] ActivityPub endpoints
- [ ] API response formats
- [ ] Database schema
- [ ] Federation protocols
- [ ] NodeInfo "software.name" field

## Testing Compatibility

### Federation Tests
1. Ensure PeachPie can follow/be followed by PyFedi instances
2. Verify post federation works bidirectionally
3. Check that activities are properly processed
4. Confirm user discovery works

### API Tests
1. Test all PyFedi API endpoints remain functional
2. Verify response formats match PyFedi
3. Check authentication mechanisms
4. Validate webhook compatibility

## Communication Strategy

### For Users
"PeachPie is an enhanced fork of PyFedi that maintains full compatibility while adding modern features like Redis Streams, advanced typing, and improved performance."

### For Instance Admins
"PeachPie instances federate seamlessly with PyFedi instances. No configuration changes needed - just enhanced performance and reliability."

### For Developers
"PeachPie builds on PyFedi's foundation with modern Python practices, better architecture, and enhanced maintainability while preserving the federation protocol."

## Success Criteria
- [ ] PeachPie instances can federate with PyFedi instances
- [ ] No breaking changes to federation protocol
- [ ] UI clearly shows PeachPie branding
- [ ] Documentation reflects new identity
- [ ] Existing PyFedi configs work with PeachPie