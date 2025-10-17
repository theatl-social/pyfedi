#!/usr/bin/env python3
"""
Simple production test for explore page - copy this to your container
"""

from app import create_app
from app.utils import topic_tree

app = create_app()
with app.app_context():
    try:
        topics = topic_tree()
        print(f"Found {len(topics)} topics")
        for t in topics:
            topic_name = t["topic"].name
            children_count = len(t["children"])
            print(f"  - {topic_name} ({children_count} children)")

        if len(topics) > 0:
            print("✅ SUCCESS: Topics are loading correctly!")
            print("The explore page should show content instead of empty container.")
        else:
            print("⚠️  No topics found in database")
            print("This explains why explore page appears empty.")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        print("This indicates the bug is still present or database issues.")
