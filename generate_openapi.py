#!/usr/bin/env python3
"""
Generate OpenAPI/Swagger JSON schema from Flask-SMOREST application
"""
import json
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def generate_openapi_spec():
    """Generate OpenAPI specification and save to file"""
    try:
        # Set required environment variables
        os.environ.setdefault('DATABASE_URL', 'sqlite:///temp.db')
        os.environ.setdefault('SERVER_NAME', 'localhost')
        os.environ.setdefault('SECRET_KEY', 'dev-key-for-schema-generation')
        
        # Import and create the Flask app
        from app import create_app
        from config import Config
        
        # Override config for schema generation
        class SchemaConfig(Config):
            TESTING = True
            SERVE_API_DOCS = True
            SQLALCHEMY_DATABASE_URI = 'sqlite:///temp.db'
            CACHE_TYPE = 'NullCache'  # Disable caching for schema generation
            CACHE_REDIS_URL = 'redis://localhost:6379/0'  # Keep default for initialization
        
        app = create_app(SchemaConfig)
        
        with app.app_context():
            # Get the OpenAPI spec from Flask-SMOREST
            from app import rest_api
            spec = rest_api.spec.to_dict()
            
            # Write to file
            output_file = project_root / 'openapi.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(spec, f, indent=2, ensure_ascii=False)
            
            print(f"✅ OpenAPI specification generated: {output_file}")
            print(f"📄 Title: {spec.get('info', {}).get('title', 'Unknown')}")
            print(f"🔢 Version: {spec.get('info', {}).get('version', 'Unknown')}")
            print(f"🛣️  Paths: {len(spec.get('paths', {}))}")
            print(f"📋 Schemas: {len(spec.get('components', {}).get('schemas', {}))}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error generating OpenAPI spec: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = generate_openapi_spec()
    sys.exit(0 if success else 1)