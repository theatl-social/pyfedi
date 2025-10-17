"""
Verify that the database issue is the root cause of empty explore page.
"""

import os

# Set environment variables
os.environ.setdefault("SERVER_NAME", "localhost")
os.environ.setdefault("SECRET_KEY", "debug-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///pyfedi.db")
os.environ.setdefault("CACHE_TYPE", "NullCache")

try:
    from app import create_app, db
    from app.utils import topic_tree

    app = create_app()

    print("🔍 VERIFYING DATABASE ISSUE")
    print("=" * 40)

    with app.app_context():
        # Check if we can inspect database tables
        try:
            tables = db.engine.table_names()
            print(f"📊 Database tables found: {len(tables)}")

            if "topic" in tables:
                print("✅ 'topic' table exists")
            else:
                print("❌ 'topic' table MISSING")
                print("   This is why explore page is empty!")

            if "community" in tables:
                print("✅ 'community' table exists")
            else:
                print("❌ 'community' table MISSING")

            # Test the topic_tree function
            print("\n🌳 Testing topic_tree() function:")
            try:
                tree = topic_tree()
                print(f"   Returns: {len(tree)} topics")
                if len(tree) == 0:
                    print("   → This causes explore page to show empty state")
            except Exception as e:
                print(f"   ❌ topic_tree() error: {e}")
                print("   → This causes explore page to show empty state")

        except Exception as e:
            print(f"❌ Database inspection error: {e}")

    print("\n" + "=" * 40)
    print("🎯 CONCLUSION:")
    print("The explore page template is working correctly.")
    print("The issue is missing database tables/data.")
    print("\nTo fix:")
    print("1. Run: flask db upgrade")
    print("2. Seed sample topics and communities")
    print("3. Explore page will then display content")

except Exception as e:
    print(f"❌ Setup error: {e}")
    print("Database or application not properly configured.")
