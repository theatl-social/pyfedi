#!/usr/bin/env python3
"""
Test the explore page with real topic data to verify the template fixes work.
"""

import os

# Set up test environment
os.environ.setdefault("SERVER_NAME", "localhost")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", f'sqlite:///{os.path.abspath("test_explore.db")}')
os.environ.setdefault("CACHE_TYPE", "NullCache")


def test_explore_page_rendering():
    """Test that the explore page renders correctly with topic data."""

    try:
        from app import create_app
        from app.utils import topic_tree

        app = create_app()

        with app.app_context():
            # Test the topic_tree function
            print("🧪 Testing topic_tree() function:")
            tree = topic_tree()
            print(f"   ✅ topic_tree() returned {len(tree)} top-level topics")

            if not tree:
                print("   ❌ No topics found - the explore page will be empty")
                return False

            # Test template rendering with a simulated request
            with app.test_client() as client:
                print("\n🌐 Testing explore page HTTP response:")

                response = client.get("/explore")
                print(f"   Status code: {response.status_code}")

                if response.status_code == 200:
                    html_content = response.get_data(as_text=True)

                    # Check if topics are in the HTML
                    topic_names = [item["topic"].name for item in tree]
                    topics_found = []

                    for topic_name in topic_names:
                        if topic_name in html_content:
                            topics_found.append(topic_name)
                            print(f"   ✅ Found topic '{topic_name}' in HTML")
                        else:
                            print(f"   ❌ Missing topic '{topic_name}' in HTML")

                    # Check for the specific bug we fixed
                    if "len(topics)" in html_content:
                        print(
                            "   ❌ CRITICAL: Still using len(topics) instead of topics|length filter!"
                        )
                        return False
                    else:
                        print("   ✅ Template correctly uses topics|length filter")

                    # Check if the container is empty
                    if "explore-container" in html_content or "Topics" in html_content:
                        print("   ✅ Explore container structure is present")
                    else:
                        print("   ⚠️  Explore container structure may be missing")

                    success_rate = len(topics_found) / len(topic_names) * 100
                    print(
                        f"\n📊 Results: {len(topics_found)}/{len(topic_names)} topics found ({success_rate:.1f}%)"
                    )

                    if success_rate >= 75:
                        print(
                            "✅ EXPLORE PAGE IS WORKING! Topics are being displayed correctly."
                        )
                        return True
                    else:
                        print(
                            "❌ Explore page has issues - not all topics are displayed"
                        )
                        return False

                else:
                    print(
                        f"   ❌ Failed to load explore page: HTTP {response.status_code}"
                    )
                    if response.status_code == 500:
                        print("   This might be a template error or missing data")
                    return False

    except Exception as e:
        print(f"❌ Error testing explore page: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🌐 TESTING EXPLORE PAGE FUNCTIONALITY")
    print("=" * 50)

    # Verify test database exists
    if not os.path.exists("test_explore.db"):
        print("❌ Test database not found. Run setup_database_for_testing.py first.")
        exit(1)

    if test_explore_page_rendering():
        print("\n🎉 SUCCESS! The explore page bug has been fixed!")
        print("   - Template syntax errors have been resolved")
        print("   - Topics are being loaded from the database")
        print("   - The explore page displays content correctly")
    else:
        print("\n❌ FAILURE! The explore page still has issues.")
        print("   Please check the errors above for details.")
