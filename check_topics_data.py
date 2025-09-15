"""
Check what topics actually exist in the database and what topic_tree() returns.
"""
import os

# Set environment variables
os.environ.setdefault('SERVER_NAME', 'localhost')
os.environ.setdefault('SECRET_KEY', 'debug-secret')
os.environ.setdefault('DATABASE_URL', 'sqlite:///pyfedi.db')  # Use actual database
os.environ.setdefault('CACHE_TYPE', 'NullCache')
os.environ.setdefault('TESTING', 'false')

try:
    from app import create_app, db
    from app.models import Topic
    from app.utils import topic_tree
    
    app = create_app()
    
    with app.app_context():
        print("🔍 CHECKING TOPICS IN DATABASE")
        print("=" * 50)
        
        # Check if database exists and has topics
        try:
            topics_count = Topic.query.count()
            print(f"📊 Total topics in database: {topics_count}")
            
            if topics_count == 0:
                print("❌ No topics found in database!")
                print("   This explains why explore page is empty.")
                print("   The page is correctly showing 'There are no communities yet.'")
            else:
                print("✅ Topics found in database:")
                topics = Topic.query.all()
                for topic in topics:
                    print(f"   - {topic.name} (machine_name: {topic.machine_name})")
                    if topic.parent_id:
                        print(f"     └─ Parent ID: {topic.parent_id}")
                
                print("\n🌳 Testing topic_tree() function:")
                tree = topic_tree()
                print(f"   topic_tree() returned {len(tree)} top-level topics")
                
                for item in tree:
                    topic = item['topic']
                    children = item['children']
                    print(f"   📁 {topic.name}")
                    for child in children:
                        print(f"      └─ {child['topic'].name}")
                
                if len(tree) == 0:
                    print("❌ topic_tree() returned empty list despite having topics!")
                    print("   This could be a bug in the topic_tree() function.")
        
        except Exception as e:
            print(f"❌ Database error: {e}")
            print("   Database might not be initialized or accessible.")
        
        print("\n" + "=" * 50)
        print("🎯 DIAGNOSIS:")
        
        if topics_count == 0:
            print("   The explore page is working correctly.")
            print("   It shows empty state because no topics exist.")
            print("   To fix: Add topics to the database.")
        else:
            print("   Topics exist but may not be displayed correctly.")
            print("   Check if topic_tree() function is working properly.")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("   Make sure you're in the correct directory and app is importable.")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()