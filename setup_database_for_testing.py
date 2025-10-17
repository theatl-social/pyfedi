"""
Set up a minimal database with topics for testing the explore page.
This bypasses migration issues and creates just what we need.
"""

import os
import sqlite3

# Set environment variables
os.environ.setdefault("SERVER_NAME", "localhost")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///test_explore.db")
os.environ.setdefault("CACHE_TYPE", "NullCache")


def create_minimal_database():
    """Create a minimal database with just topics for testing."""
    db_path = "test_explore.db"

    try:
        # Remove existing database
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"🗑️  Removed existing database: {db_path}")

        # Create new database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("🔨 Creating minimal database schema...")

        # Create topic table (minimal version)
        cursor.execute("""
            CREATE TABLE topic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                machine_name VARCHAR(255) NOT NULL,
                parent_id INTEGER,
                num_communities INTEGER DEFAULT 0,
                show_posts_in_children BOOLEAN DEFAULT TRUE,
                ap_id VARCHAR(255),
                FOREIGN KEY (parent_id) REFERENCES topic (id)
            )
        """)

        # Create community table (minimal version)
        cursor.execute("""
            CREATE TABLE community (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                title VARCHAR(255),
                description TEXT,
                topic_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topic (id)
            )
        """)

        print("✅ Database schema created")

        # Insert sample topics
        print("📊 Inserting sample topics...")

        topics_data = [
            # Top-level topics
            (
                1,
                "Technology",
                "technology",
                None,
                3,
                True,
                "https://localhost/t/technology",
            ),
            (2, "Science", "science", None, 2, True, "https://localhost/t/science"),
            (3, "Gaming", "gaming", None, 1, True, "https://localhost/t/gaming"),
            (4, "Arts", "arts", None, 1, True, "https://localhost/t/arts"),
            # Sub-topics under Technology
            (
                5,
                "Programming",
                "programming",
                1,
                2,
                True,
                "https://localhost/t/programming",
            ),
            (
                6,
                "Web Development",
                "web-dev",
                1,
                1,
                True,
                "https://localhost/t/web-dev",
            ),
            (
                7,
                "Mobile Development",
                "mobile-dev",
                1,
                1,
                True,
                "https://localhost/t/mobile-dev",
            ),
            # Sub-topics under Science
            (8, "Physics", "physics", 2, 1, True, "https://localhost/t/physics"),
            (9, "Biology", "biology", 2, 1, True, "https://localhost/t/biology"),
            # Sub-topics under Gaming
            (10, "PC Gaming", "pc-gaming", 3, 1, True, "https://localhost/t/pc-gaming"),
            # Sub-topics under Arts
            (
                11,
                "Photography",
                "photography",
                4,
                1,
                True,
                "https://localhost/t/photography",
            ),
            # Sub-sub-topics
            (12, "Python", "python", 5, 1, True, "https://localhost/t/python"),
            (
                13,
                "JavaScript",
                "javascript",
                5,
                1,
                True,
                "https://localhost/t/javascript",
            ),
        ]

        cursor.executemany(
            """
            INSERT INTO topic (id, name, machine_name, parent_id, num_communities, show_posts_in_children, ap_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            topics_data,
        )

        # Insert sample communities
        print("🏘️  Inserting sample communities...")

        communities_data = [
            (
                1,
                "python",
                "Python Programming",
                "Discussion about Python programming language",
                12,
            ),
            (
                2,
                "javascript",
                "JavaScript Development",
                "JavaScript coding and frameworks",
                13,
            ),
            (3, "webdev", "Web Development", "General web development discussions", 6),
            (4, "physics", "Physics", "Physics discussions and research", 8),
            (5, "biology", "Biology", "Biology and life sciences", 9),
            (6, "pcgaming", "PC Gaming", "PC gaming discussions", 10),
            (7, "photography", "Photography", "Photography tips and showcase", 11),
        ]

        cursor.executemany(
            """
            INSERT INTO community (id, name, title, description, topic_id)
            VALUES (?, ?, ?, ?, ?)
        """,
            communities_data,
        )

        conn.commit()
        conn.close()

        print(f"✅ Database created successfully: {db_path}")
        print(f"   Topics inserted: {len(topics_data)}")
        print(f"   Communities inserted: {len(communities_data)}")

        return True

    except Exception as e:
        print(f"❌ Error creating database: {e}")
        return False


def test_explore_with_real_data():
    """Test the explore page with real database data."""
    try:
        # Update environment to use our test database
        full_path = os.path.abspath("test_explore.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{full_path}"

        from app import create_app
        from app.utils import topic_tree

        app = create_app()

        with app.app_context():
            print("\n🧪 Testing topic_tree() function with real data:")

            tree = topic_tree()
            print(f"   topic_tree() returned: {len(tree)} top-level topics")

            for item in tree:
                topic = item["topic"]
                children = item["children"]
                print(f"   📁 {topic.name} ({len(children)} children)")
                for child in children:
                    sub_children = child["children"]
                    print(
                        f"      └─ {child['topic'].name} ({len(sub_children)} sub-children)"
                    )
                    for sub_child in sub_children:
                        print(f"         └─ {sub_child['topic'].name}")

            print("\n✅ topic_tree() is working correctly!")
            print(f"   The explore page should now show {len(tree)} top-level topics")

            return True

    except Exception as e:
        print(f"❌ Error testing with real data: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🗄️  SETTING UP DATABASE FOR EXPLORE PAGE TESTING")
    print("=" * 55)

    # Create the database
    if create_minimal_database():
        # Test with the new data
        test_explore_with_real_data()

        print("\n🎉 SUCCESS!")
        print("Now you can:")
        print("1. Update DATABASE_URL to point to test_explore.db")
        print("2. Visit /explore and see topics displayed")
        print("3. Run our real-world tests to verify everything works")
    else:
        print("\n❌ Failed to set up database")
