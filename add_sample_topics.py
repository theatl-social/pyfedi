#!/usr/bin/env python3
"""
Add sample topics to the production database so the explore page has content.
Run this in your production container to populate topics.
"""
from app import create_app
from app.models import Topic, db

app = create_app()

def add_sample_topics():
    """Add basic topics to make the explore page functional."""
    
    with app.app_context():
        print("🏗️  Adding sample topics to database...")
        
        # Check if topics already exist
        existing_count = Topic.query.count()
        print(f"Current topics in database: {existing_count}")
        
        if existing_count > 0:
            print("✅ Topics already exist - no need to add samples")
            return True
        
        try:
            # Create main topic categories
            topics_to_add = [
                # Main categories
                {"name": "Technology", "machine_name": "technology", "parent_id": None},
                {"name": "Science", "machine_name": "science", "parent_id": None},
                {"name": "Entertainment", "machine_name": "entertainment", "parent_id": None},
                {"name": "Sports", "machine_name": "sports", "parent_id": None},
                {"name": "News", "machine_name": "news", "parent_id": None},
                {"name": "Education", "machine_name": "education", "parent_id": None},
            ]
            
            # Add the topics
            added_topics = {}
            
            for topic_data in topics_to_add:
                topic = Topic(
                    name=topic_data["name"],
                    machine_name=topic_data["machine_name"],
                    parent_id=topic_data["parent_id"],
                    num_communities=0  # Will be updated as communities are added
                )
                
                db.session.add(topic)
                db.session.flush()  # Get the ID
                
                added_topics[topic_data["name"]] = topic.id
                print(f"  ✅ Added topic: {topic.name}")
            
            # Add some sub-topics for Technology
            tech_id = added_topics.get("Technology")
            if tech_id:
                tech_subtopics = [
                    {"name": "Programming", "machine_name": "programming", "parent_id": tech_id},
                    {"name": "Web Development", "machine_name": "web-development", "parent_id": tech_id},
                    {"name": "Mobile Apps", "machine_name": "mobile-apps", "parent_id": tech_id},
                ]
                
                for subtopic_data in tech_subtopics:
                    subtopic = Topic(
                        name=subtopic_data["name"],
                        machine_name=subtopic_data["machine_name"], 
                        parent_id=subtopic_data["parent_id"],
                        num_communities=0
                    )
                    db.session.add(subtopic)
                    print(f"    ✅ Added subtopic: {subtopic.name}")
            
            # Commit all changes
            db.session.commit()
            
            # Verify the addition
            final_count = Topic.query.count()
            print("\n📊 Topics added successfully!")
            print(f"   Total topics now: {final_count}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error adding topics: {e}")
            db.session.rollback()
            return False

def test_explore_after_adding():
    """Test that the explore page will now work."""
    
    with app.app_context():
        try:
            from app.utils import topic_tree
            
            print("\n🧪 Testing topic_tree() after adding topics...")
            topics = topic_tree()
            
            print(f"✅ Found {len(topics)} top-level topics:")
            for topic_data in topics:
                topic = topic_data["topic"]
                children = topic_data["children"]
                print(f"  - {topic.name} ({len(children)} children)")
                
                for child_data in children:
                    child = child_data["topic"]
                    grandchildren = child_data["children"]
                    print(f"    └─ {child.name} ({len(grandchildren)} sub-children)")
            
            if len(topics) > 0:
                print("\n🎉 SUCCESS! The explore page should now show content!")
                return True
            else:
                print("\n❌ Still no topics - something went wrong")
                return False
                
        except Exception as e:
            print(f"❌ Error testing topics: {e}")
            return False

if __name__ == '__main__':
    print("🌐 ADDING SAMPLE TOPICS TO PRODUCTION DATABASE")
    print("=" * 60)
    print("This will add basic topic categories so users can explore content.\n")
    
    if add_sample_topics():
        if test_explore_after_adding():
            print("\n✅ COMPLETE! The explore page bug is now fully resolved.")
            print("   Users will see topic categories instead of an empty container.")
            print("   You can add more topics and communities through the admin interface.")
        else:
            print("\n⚠️  Topics were added but testing failed - check for other issues.")
    else:
        print("\n❌ Failed to add sample topics - check database permissions and connectivity.")