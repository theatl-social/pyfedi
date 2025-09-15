"""
Test the explore page functionality to ensure it displays content correctly.

This test verifies that the explore page bug is actually fixed by checking
the template syntax and route behavior.
"""
import os
import re

# Set environment variables before importing Flask app
os.environ.setdefault('SERVER_NAME', 'test.localhost')
os.environ.setdefault('SECRET_KEY', 'test-secret-for-explore-test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///memory:test.db')
os.environ.setdefault('CACHE_TYPE', 'NullCache')
os.environ.setdefault('CACHE_REDIS_URL', 'memory://')
os.environ.setdefault('CELERY_BROKER_URL', 'memory://localhost/')
os.environ.setdefault('TESTING', 'true')

import pytest
from flask import url_for


def test_explore_template_syntax():
    """Test that the explore template has correct Jinja2 syntax."""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'app', 'templates', 'explore.html'
    )
    
    if not os.path.exists(template_path):
        pytest.skip("explore.html template not found")
    
    with open(template_path, 'r') as f:
        template_content = f.read()
    
    # Check that the template doesn't use Python's len() function
    assert 'len(topics)' not in template_content, "Template uses Python len() instead of Jinja2 |length filter"
    assert 'len(communities)' not in template_content, "Template uses Python len() instead of Jinja2 |length filter"
    
    # Check that it uses proper Jinja2 syntax
    if 'topics' in template_content:
        # Should use |length filter, not len() function
        length_patterns = [
            r'topics\s*\|\s*length',
            r'communities\s*\|\s*length'
        ]
        has_proper_syntax = any(re.search(pattern, template_content) for pattern in length_patterns)
        
        # Only check if the template actually checks lengths
        if 'length' in template_content or 'len(' in template_content:
            assert has_proper_syntax, "Template should use |length filter for Jinja2 compatibility"


def test_explore_route_exists():
    """Test that the explore route is properly defined."""
    from app import create_app
    
    app = create_app()
    
    with app.app_context():
        # Check that the route exists
        assert '/explore' in [rule.rule for rule in app.url_map.iter_rules()], "Explore route not found"
        
        # Check that we can generate the URL
        with app.test_request_context():
            explore_url = url_for('main.explore')
            assert explore_url == '/explore'


def test_all_templates_use_correct_length_syntax():
    """Test that all templates use |length instead of len()."""
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'app', 'templates'
    )
    
    if not os.path.exists(templates_dir):
        pytest.skip("Templates directory not found")
    
    problematic_files = []
    
    # Walk through all template files
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith('.html'):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, templates_dir)
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        content = f.read()
                        # Check for Python len() usage in Jinja2 context
                        if re.search(r'\{\%.*len\s*\(.*\%\}', content) or re.search(r'\{\{.*len\s*\(.*\}\}', content):
                            problematic_files.append(rel_path)
                    except UnicodeDecodeError:
                        # Skip binary files
                        continue
    
    if problematic_files:
        files_list = '\n'.join(f"  - {f}" for f in problematic_files)
        pytest.fail(
            f"Found templates using Python len() instead of |length filter:\n{files_list}\n"
            f"These should use |length filter for Jinja2 compatibility."
        )


if __name__ == '__main__':
    # Allow running this test standalone
    import sys
    import subprocess
    
    # Run the tests
    result = subprocess.run([
        sys.executable, '-m', 'pytest', __file__, '-v'
    ], cwd=os.path.dirname(os.path.dirname(__file__)))
    
    sys.exit(result.returncode)