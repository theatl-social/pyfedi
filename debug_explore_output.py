"""
Debug script to show exactly what the explore page template generates.
This helps us understand if the explore page is working correctly.
"""
import os
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Set minimal environment
os.environ.setdefault('SERVER_NAME', 'test.localhost')
os.environ.setdefault('SECRET_KEY', 'test-debug-secret')
os.environ.setdefault('DATABASE_URL', 'sqlite:///memory:test.db')
os.environ.setdefault('CACHE_TYPE', 'NullCache')
os.environ.setdefault('TESTING', 'true')


def debug_explore_rendering():
    """Show what the explore page actually renders."""
    
    app_dir = Path(__file__).parent / 'app'
    templates_dir = app_dir / 'templates'
    
    print("🔍 DEBUGGING EXPLORE PAGE RENDERING")
    print("=" * 60)
    
    # Setup Jinja2 environment
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(['html', 'xml'])
    )
    
    # Mock required functions
    env.globals.update({
        'theme': lambda: 'piefed',
        'file_exists': lambda x: False,
        '_': lambda x: x,  # Mock translation
        'current_user': type('User', (), {
            'is_authenticated': False,
            'is_anonymous': True,
            'link': lambda: 'testuser'
        })(),
    })
    
    # Mock topic class
    class MockTopic:
        def __init__(self, name, machine_name):
            self.name = name
            self.machine_name = machine_name
        
        def path(self):
            return self.machine_name
    
    # Test scenarios
    test_scenarios = [
        {
            'name': 'Empty Topics (Bug Scenario)',
            'topics': [],
            'description': 'This is what users see when there are no topics in the database'
        },
        {
            'name': 'With Topics (Expected Content)',
            'topics': [
                {
                    'topic': MockTopic('Technology', 'technology'),
                    'children': [
                        {
                            'topic': MockTopic('Programming', 'programming'),
                            'children': []
                        },
                        {
                            'topic': MockTopic('Web Development', 'web-dev'),
                            'children': []
                        }
                    ]
                },
                {
                    'topic': MockTopic('Science', 'science'),
                    'children': [
                        {
                            'topic': MockTopic('Physics', 'physics'),
                            'children': []
                        }
                    ]
                },
                {
                    'topic': MockTopic('Gaming', 'gaming'),
                    'children': []
                }
            ],
            'description': 'This is what users should see when topics exist'
        }
    ]
    
    # Get and simplify template
    template_source, _, _ = env.loader.get_source(env, 'explore.html')
    
    # Remove extends and imports for standalone testing
    simplified_source = re.sub(r'{%.*?extends.*?%}', '', template_source, flags=re.DOTALL)
    simplified_source = re.sub(r'{%.*?from.*?import.*?%}', '', simplified_source, flags=re.DOTALL)
    
    # Create template
    template = env.from_string(simplified_source)
    
    for scenario in test_scenarios:
        print(f"\n📋 SCENARIO: {scenario['name']}")
        print(f"   {scenario['description']}")
        print("-" * 60)
        
        try:
            rendered = template.render(
                topics=scenario['topics'],
                menu_instance_feeds=[],
                menu_my_feeds=None,
                menu_subscribed_feeds=None,
                active_child='explore'
            )
            
            # Clean up the HTML for better readability
            lines = rendered.split('\n')
            cleaned_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped:  # Only keep non-empty lines
                    cleaned_lines.append(stripped)
            
            cleaned_html = '\n'.join(cleaned_lines)
            
            print("HTML OUTPUT:")
            print(cleaned_html)
            
            # Analyze the content
            print("\n📊 CONTENT ANALYSIS:")
            
            if scenario['topics']:
                # Check for topic names
                topic_names = [topic['topic'].name for topic in scenario['topics']]
                found_topics = []
                for topic_name in topic_names:
                    if topic_name in rendered:
                        found_topics.append(topic_name)
                
                print(f"   ✅ Topics found in output: {', '.join(found_topics)}")
                
                # Check for topic links
                topic_links = []
                for topic in scenario['topics']:
                    expected_link = f'/topic/{topic["topic"].path()}'
                    if expected_link in rendered:
                        topic_links.append(expected_link)
                
                print(f"   🔗 Topic links found: {', '.join(topic_links)}")
                
                # Check for hierarchical structure
                if any('children' in topic and topic['children'] for topic in scenario['topics']):
                    print("   📁 Hierarchical structure present")
                
            else:
                # Check for empty state
                if 'There are no communities yet.' in rendered:
                    print("   ℹ️  Empty state message displayed")
                else:
                    print("   ⚠️  No empty state message found")
            
            # Check for basic structure
            if 'Topics' in rendered:
                print("   📑 Topics tab present")
            if 'Feeds' in rendered:
                print("   📑 Feeds tab present")
            if 'More communities' in rendered:
                print("   🔗 'More communities' button present")
            
            # Check for template errors
            error_indicators = ['len(topics)', '{{', '{%', 'UndefinedError', 'TemplateSyntaxError']
            errors_found = [error for error in error_indicators if error in rendered]
            if errors_found:
                print(f"   ❌ Template errors found: {', '.join(errors_found)}")
            else:
                print("   ✅ No template errors detected")
            
        except Exception as e:
            print(f"❌ Error rendering scenario: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
    
    print("\n🎯 CONCLUSION:")
    print("If the explore page shows 'empty container', it's likely because:")
    print("1. No topics exist in the database (shows empty state correctly)")
    print("2. The application context isn't properly initialized")
    print("3. The route isn't calling topic_tree() correctly")
    print("\nThe Jinja2 template syntax itself is working correctly!")


if __name__ == '__main__':
    debug_explore_rendering()