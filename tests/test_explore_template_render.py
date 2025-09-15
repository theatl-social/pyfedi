"""
Test the explore template rendering in isolation.

This test verifies that the explore template renders correctly with different
data scenarios without requiring full application context.
"""
import os
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError


def test_explore_template_renders_with_empty_topics():
    """Test that explore template renders when topics list is empty."""
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'app', 'templates'
    )
    
    if not os.path.exists(templates_dir):
        pytest.skip("Templates directory not found")
    
    # Create Jinja2 environment
    env = Environment(loader=FileSystemLoader(templates_dir))
    
    # Mock the custom functions and filters
    def mock_theme():
        return 'piefed'
    
    def mock_file_exists(path):
        return False
    
    def mock_translate(text):
        return text
    
    # Add functions to globals (not filters)
    env.globals['theme'] = mock_theme
    env.globals['file_exists'] = mock_file_exists
    env.globals['_'] = mock_translate
    env.globals['current_user'] = type('MockUser', (), {
        'is_authenticated': False,
        'is_anonymous': True,
        'link': lambda: 'testuser'
    })()
    
    try:
        template = env.get_template('explore.html')
        
        # Test with empty topics
        rendered = template.render(
            topics=[],
            menu_instance_feeds=[],
            menu_my_feeds=None,
            menu_subscribed_feeds=None
        )
        
        # Should render without errors
        assert rendered is not None
        assert len(rendered) > 0
        
        # Should contain the empty state message
        assert 'There are no communities yet.' in rendered
        
        # Should contain basic structure
        assert 'Topics' in rendered
        assert 'Feeds' in rendered
        
        print("✅ Empty topics test passed")
        
    except TemplateSyntaxError as e:
        raise AssertionError(f"Template syntax error: {e}")


def test_explore_template_renders_with_topics():
    """Test that explore template renders when topics exist."""
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'app', 'templates'
    )
    
    if not os.path.exists(templates_dir):
        pytest.skip("Templates directory not found")
    
    # Mock topic object
    class MockTopic:
        def __init__(self, name):
            self.name = name
        
        def path(self):
            return self.name.lower().replace(' ', '-')
    
    # Create mock topic tree structure
    mock_topics = [
        {
            'topic': MockTopic('Technology'),
            'children': [
                {
                    'topic': MockTopic('Programming'), 
                    'children': []
                }
            ]
        },
        {
            'topic': MockTopic('Science'),
            'children': []
        }
    ]
    
    # Create Jinja2 environment
    env = Environment(loader=FileSystemLoader(templates_dir))
    
    # Mock the custom functions and globals
    env.globals['theme'] = lambda: 'piefed'
    env.globals['file_exists'] = lambda path: False
    env.globals['_'] = lambda text: text
    env.globals['current_user'] = type('MockUser', (), {
        'is_authenticated': False,
        'is_anonymous': True,
        'link': lambda: 'testuser'
    })()
    
    try:
        template = env.get_template('explore.html')
        
        # Test with topics
        rendered = template.render(
            topics=mock_topics,
            menu_instance_feeds=[],
            menu_my_feeds=None,
            menu_subscribed_feeds=None
        )
        
        # Should render without errors
        assert rendered is not None
        assert len(rendered) > 0
        
        # Should contain topic names
        assert 'Technology' in rendered
        assert 'Science' in rendered
        assert 'Programming' in rendered
        
        # Should NOT contain empty state message
        assert 'There are no communities yet.' not in rendered
        
        print("✅ With topics test passed")
        
    except TemplateSyntaxError as e:
        raise AssertionError(f"Template syntax error: {e}")


def test_explore_template_length_filter_usage():
    """Test that the template correctly uses |length filter."""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        'app', 'templates', 'explore.html'
    )
    
    if not os.path.exists(template_path):
        pytest.skip("explore.html template not found")
    
    with open(template_path, 'r') as f:
        template_content = f.read()
    
    # The critical line that was causing the bug
    assert 'topics|length > 0' in template_content, "Template should use |length filter on line 20"
    
    # Make sure it doesn't use the old buggy syntax
    assert 'len(topics)' not in template_content, "Template should not use Python len() function"
    
    print("✅ Length filter usage test passed")


if __name__ == '__main__':
    """Run tests standalone."""
    import sys
    
    try:
        test_explore_template_length_filter_usage()
        test_explore_template_renders_with_empty_topics()
        test_explore_template_renders_with_topics()
        
        print("\n🎉 All explore template tests passed!")
        print("The template syntax bug has been fixed and the template renders correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)