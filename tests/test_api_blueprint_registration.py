#!/usr/bin/env python3
"""
Test to verify all API blueprints are properly registered and their routes are accessible.
This test ensures no API endpoints return 404 due to missing blueprint registration.
"""
import pytest
from flask import Flask
from app import create_app
import re


def test_all_api_blueprints_registered():
    """Verify all defined API blueprints are properly registered."""
    app = create_app()
    
    # Expected API blueprints that should be registered
    expected_api_blueprints = {
        'Site',           # site_bp
        'Misc',           # misc_bp
        'Community',      # comm_bp
        'Feed',           # feed_bp
        'Topic',          # topic_bp
        'User',           # user_bp
        'Comment',        # reply_bp
        'Post',           # post_bp
        'Private Message',# private_message_bp
        'Upload',         # upload_bp
        'Admin',          # admin_bp (special case with different prefix)
    }
    
    # Get all registered blueprints from the Flask-Smorest API
    registered_blueprints = set()
    if hasattr(app.extensions, 'smorest'):
        api = app.extensions.get('smorest')
        if api and hasattr(api, '_app'):
            for bp in api._app.blueprints.values():
                if hasattr(bp, 'name') and bp.name != 'api_alpha':
                    registered_blueprints.add(bp.name)
    
    # Check if all expected blueprints are registered
    missing_blueprints = expected_api_blueprints - registered_blueprints
    
    assert not missing_blueprints, f"Missing API blueprints: {missing_blueprints}"
    
    print(f"✅ All {len(expected_api_blueprints)} API blueprints are registered")
    return True


def test_api_routes_accessible():
    """Test that critical API routes are accessible (not 404)."""
    app = create_app()
    
    with app.test_client() as client:
        # Test routes that should exist (even if they return 400 due to missing auth)
        test_routes = [
            ('/api/alpha/site', 'GET'),
            ('/api/alpha/site/version', 'GET'),
            ('/api/alpha/community/list', 'GET'),
            ('/api/alpha/post/list', 'GET'),
            ('/api/alpha/comment/list', 'GET'),
            ('/api/alpha/private_message/list', 'GET'),
            ('/api/alpha/user/unread_count', 'GET'),
            ('/api/alpha/topic/list', 'GET'),
            ('/api/alpha/feed/list', 'GET'),
            ('/api/alpha/search', 'GET'),
            ('/api/alpha/federated_instances', 'GET'),
        ]
        
        failed_routes = []
        
        for route, method in test_routes:
            if method == 'GET':
                response = client.get(route)
            elif method == 'POST':
                response = client.post(route)
            else:
                continue
            
            # We expect 400 (api not enabled) or 401/403 (auth required), but NOT 404
            if response.status_code == 404:
                failed_routes.append(f"{method} {route}: returned 404")
            else:
                print(f"✅ {method} {route}: {response.status_code} (route exists)")
        
        assert not failed_routes, "Routes returning 404:\n" + "\n".join(failed_routes)
    
    print(f"✅ All {len(test_routes)} tested API routes are accessible (not 404)")
    return True


def test_blueprint_route_coverage():
    """Verify each blueprint has at least one route defined."""
    app = create_app()
    
    # Map of blueprint names to expected route patterns
    blueprint_route_patterns = {
        'Site': r'/api/alpha/site',
        'Misc': r'/api/alpha/(search|resolve_object|federated_instances)',
        'Community': r'/api/alpha/community',
        'Feed': r'/api/alpha/feed',
        'Topic': r'/api/alpha/topic',
        'User': r'/api/alpha/user',
        'Comment': r'/api/alpha/comment',
        'Post': r'/api/alpha/post',
        'Private Message': r'/api/alpha/private_message',
        'Upload': r'/api/alpha/upload',
        'Admin': r'/api/alpha/admin',
    }
    
    # Get all registered routes
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(str(rule))
    
    # Check each blueprint has routes
    missing_routes = []
    for bp_name, pattern in blueprint_route_patterns.items():
        if not any(re.search(pattern, route) for route in routes):
            missing_routes.append(f"{bp_name}: no routes matching {pattern}")
    
    assert not missing_routes, "Blueprints without routes:\n" + "\n".join(missing_routes)
    
    print("✅ All blueprints have routes defined")
    return True


def test_api_blueprint_imports():
    """Verify all blueprints can be imported from app.api.alpha."""
    try:
        from app.api.alpha import (
            bp, site_bp, misc_bp, comm_bp, feed_bp, topic_bp, 
            user_bp, reply_bp, post_bp, private_message_bp, 
            upload_bp, admin_bp
        )
        
        blueprints = {
            'bp': bp,
            'site_bp': site_bp,
            'misc_bp': misc_bp,
            'comm_bp': comm_bp,
            'feed_bp': feed_bp,
            'topic_bp': topic_bp,
            'user_bp': user_bp,
            'reply_bp': reply_bp,
            'post_bp': post_bp,
            'private_message_bp': private_message_bp,
            'upload_bp': upload_bp,
            'admin_bp': admin_bp,
        }
        
        # Verify each blueprint is not None
        for name, blueprint in blueprints.items():
            assert blueprint is not None, f"{name} is None"
            print(f"✅ {name} imported successfully")
        
        print(f"✅ All {len(blueprints)} blueprints can be imported")
        return True
        
    except ImportError as e:
        pytest.fail(f"Failed to import blueprints: {e}")


if __name__ == '__main__':
    # Run tests directly
    import sys
    
    print("🔍 Testing API Blueprint Registration\n")
    
    try:
        print("1. Testing blueprint imports...")
        test_api_blueprint_imports()
        print()
        
        print("2. Testing all blueprints are registered...")
        test_all_api_blueprints_registered()
        print()
        
        print("3. Testing API routes are accessible...")
        test_api_routes_accessible()
        print()
        
        print("4. Testing blueprint route coverage...")
        test_blueprint_route_coverage()
        print()
        
        print("✅ All API blueprint tests passed!")
        sys.exit(0)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)