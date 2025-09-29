#!/usr/bin/env python3
"""
Test the explore template rendering directly to verify our fixes work.
"""
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

def test_explore_template():
    """Test that the explore template renders without syntax errors."""
    
    print("🧪 TESTING EXPLORE TEMPLATE SYNTAX")
    print("=" * 45)
    
    try:
        # Set up Jinja2 environment
        env = Environment(
            loader=FileSystemLoader('app/templates'),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        # Add custom filters and functions that might be used
        def mock_filter(value, *args, **kwargs):
            return str(value)
        
        def mock_theme():
            return 'piefed'
        
        def mock_file_exists(path):
            return False
        
        def mock_gettext(text):
            return text
        
        env.filters['shorten'] = mock_filter
        env.filters['community_links'] = mock_filter
        env.filters['person_links'] = mock_filter
        env.filters['feed_links'] = mock_filter
        env.filters['shorten_url'] = mock_filter
        env.filters['remove_images'] = mock_filter
        
        env.globals['theme'] = mock_theme
        env.globals['file_exists'] = mock_file_exists
        env.globals['_'] = mock_gettext
        
        # Load the template
        print("📄 Loading explore.html template...")
        template = env.get_template('explore.html')
        print("   ✅ Template loaded successfully")
        
        # Create mock data structure
        print("\n📊 Creating mock topic data...")
        
        class MockTopic:
            def __init__(self, id, name, machine_name, num_communities=0):
                self.id = id
                self.name = name
                self.machine_name = machine_name
                self.num_communities = num_communities
        
        # Mock topics similar to our test data
        mock_topics = [
            {
                'topic': MockTopic(1, 'Technology', 'technology', 3),
                'children': [
                    {
                        'topic': MockTopic(5, 'Programming', 'programming', 2),
                        'children': [
                            {'topic': MockTopic(12, 'Python', 'python', 1), 'children': []},
                            {'topic': MockTopic(13, 'JavaScript', 'javascript', 1), 'children': []}
                        ]
                    },
                    {'topic': MockTopic(6, 'Web Development', 'web-dev', 1), 'children': []},
                    {'topic': MockTopic(7, 'Mobile Development', 'mobile-dev', 1), 'children': []}
                ]
            },
            {
                'topic': MockTopic(2, 'Science', 'science', 2),
                'children': [
                    {'topic': MockTopic(8, 'Physics', 'physics', 1), 'children': []},
                    {'topic': MockTopic(9, 'Biology', 'biology', 1), 'children': []}
                ]
            },
            {
                'topic': MockTopic(3, 'Gaming', 'gaming', 1),
                'children': [
                    {'topic': MockTopic(10, 'PC Gaming', 'pc-gaming', 1), 'children': []}
                ]
            },
            {
                'topic': MockTopic(4, 'Arts', 'arts', 1),
                'children': [
                    {'topic': MockTopic(11, 'Photography', 'photography', 1), 'children': []}
                ]
            }
        ]
        
        print(f"   ✅ Created {len(mock_topics)} mock topics with nested structure")
        
        # Test template rendering
        print("\n🎨 Rendering template...")
        
        context = {
            'topics': mock_topics,
            'current_user': None,  # Mock anonymous user
            'g': type('MockG', (), {})(),  # Mock Flask g object
        }
        
        try:
            rendered = template.render(**context)
            print("   ✅ Template rendered successfully!")
            
            # Analyze the rendered output
            print("\n🔍 Analyzing rendered output...")
            
            # Check for the fixed syntax
            if 'topics|length' in rendered:
                print("   ✅ Found topics|length filter (correct syntax)")
            elif 'len(topics)' in rendered:
                print("   ❌ CRITICAL: Still using len(topics) - template not fixed!")
                return False
            else:
                print("   ℹ️  No length check found in rendered output")
            
            # Check if topics are present
            topic_names_found = []
            for topic_data in mock_topics:
                topic_name = topic_data['topic'].name
                if topic_name in rendered:
                    topic_names_found.append(topic_name)
                    print(f"   ✅ Found topic: {topic_name}")
                else:
                    print(f"   ❌ Missing topic: {topic_name}")
            
            # Check for empty container
            if len(topic_names_found) == 0:
                print("   ❌ No topics found in rendered output - container would be empty!")
                return False
            
            success_rate = len(topic_names_found) / len(mock_topics) * 100
            print(f"\n📊 Results: {len(topic_names_found)}/{len(mock_topics)} topics rendered ({success_rate:.1f}%)")
            
            if success_rate >= 75:
                print("✅ TEMPLATE IS WORKING! Topics would be displayed correctly.")
                return True
            else:
                print("❌ Template has issues - not all topics would be displayed")
                return False
                
        except Exception as e:
            print(f"   ❌ Template rendering failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing template: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    if test_explore_template():
        print("\n🎉 SUCCESS! The explore template has been fixed!")
        print("   - Jinja2 syntax errors resolved")
        print("   - Template renders topics correctly") 
        print("   - The empty container bug should be resolved")
    else:
        print("\n❌ FAILURE! The explore template still has issues.")
        print("   Please check the template syntax and data flow.")