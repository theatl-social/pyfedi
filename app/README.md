# PyFedi Application Directory

This is the main application directory containing all the modules and components that make up PyFedi.

## Directory Structure

### Core Modules
- **`__init__.py`** - Flask application factory and initialization
- **`cli.py`** - Command-line interface commands
- **`models.py`** - SQLAlchemy database models
- **`constants.py`** - Application-wide constants
- **`utils.py`** - Utility functions and helpers
- **`enhancements.py`** - PyFedi-specific enhancements

### Feature Modules
- **`activitypub/`** - ActivityPub protocol implementation
- **`federation/`** - Federation system with Redis Streams
- **`admin/`** - Administrative interface
- **`auth/`** - Authentication and authorization
- **`community/`** - Community management
- **`post/`** - Post and content handling
- **`user/`** - User profiles and management
- **`chat/`** - Direct messaging system
- **`search/`** - Search functionality
- **`feed/`** - Feed aggregation features

### API Modules
- **`api/`** - API endpoints
  - **`alpha/`** - Alpha API implementation

### Support Modules
- **`domain/`** - Domain management
- **`instance/`** - Instance configuration
- **`security/`** - Security features and protections
- **`shared/`** - Shared utilities and tasks
- **`topic/`** - Topic categorization
- **`tag/`** - Tagging system
- **`dev/`** - Development utilities
- **`main/`** - Main routes and homepage

### Static Assets
- **`static/`** - CSS, JavaScript, images
- **`templates/`** - Jinja2 HTML templates

## Key Components

### Application Factory
The application is created using the Flask application factory pattern in `__init__.py`. This allows for easy testing and multiple configurations.

### Database Models
All database models are defined in `models.py` using SQLAlchemy 2.0 with full type annotations.

### Federation System
The new Redis Streams-based federation system is in the `federation/` directory, replacing the legacy Celery implementation.

### ActivityPub Implementation
Complete ActivityPub protocol support is implemented in the `activitypub/` directory with modular route handlers.

## Development

### Running the Application
```bash
flask run
```

### Running CLI Commands
```bash
flask cli <command>
```

### Testing
```bash
pytest
```

## Architecture Decisions

1. **Modular Structure**: Each feature area has its own module with routes, utilities, and templates
2. **Type Safety**: Full Python 3.13 type annotations throughout
3. **Redis Streams**: Modern message queue system for federation
4. **Blueprint Organization**: Flask blueprints for route organization
5. **Separation of Concerns**: Clear boundaries between modules