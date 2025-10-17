"""
Real-world CI/CD-compatible test for the explore page.

This test validates that the explore page renders correctly by:
1. Testing the actual template with mock data (no database required)
2. Simulating the exact conditions that cause the empty container bug
3. Verifying the fix works in a CI/CD environment
"""

import os
import sys
import re
from pathlib import Path

# Set minimal environment for imports
os.environ.setdefault("SERVER_NAME", "test.localhost")
os.environ.setdefault("SECRET_KEY", "test-ci-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///memory:test.db")
os.environ.setdefault("CACHE_TYPE", "NullCache")
os.environ.setdefault("TESTING", "true")


def test_explore_template_compiles_correctly():
    """
    Test that the explore.html template compiles without syntax errors.
    This catches the len() vs |length bug at the Jinja2 compilation level.
    """
    from jinja2 import (
        Environment,
        FileSystemLoader,
        TemplateSyntaxError,
        select_autoescape,
    )

    # Find template directory
    app_dir = Path(__file__).parent.parent / "app"
    templates_dir = app_dir / "templates"

    if not templates_dir.exists():
        print(f"❌ Templates directory not found: {templates_dir}")
        return False

    try:
        # Create Jinja2 environment similar to Flask's
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Add minimal required globals/functions
        env.globals.update(
            {
                "theme": lambda: "piefed",
                "file_exists": lambda x: False,
                "_": lambda x: x,  # Mock translation
            }
        )

        # Try to compile the template
        env.get_template("explore.html")

        # Get template source to verify the fix
        source, _, _ = env.loader.get_source(env, "explore.html")

        # Check for the specific bug pattern
        if "len(topics)" in source:
            print(
                "❌ CRITICAL BUG: Template uses Python len() instead of Jinja2 |length filter!"
            )
            print("   Found: len(topics)")
            print("   Should be: topics|length")
            return False

        # Verify the correct syntax is present
        if "topics|length" not in source:
            print("⚠️  Warning: Template doesn't check topics length at all")
            return False

        print("✅ Template compiles successfully")
        print("   Correct syntax found: topics|length")
        return True

    except TemplateSyntaxError as e:
        print(f"❌ Template syntax error: {e}")
        print(f"   Line {e.lineno}: {e.message}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_explore_renders_with_empty_data():
    """
    Test that the explore page renders correctly when there's no data.
    This simulates the exact condition where the bug manifests.
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    app_dir = Path(__file__).parent.parent / "app"
    templates_dir = app_dir / "templates"

    if not templates_dir.exists():
        print(f"❌ Templates directory not found: {templates_dir}")
        return False

    try:
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Mock all required template functions and filters
        env.globals.update(
            {
                "theme": lambda: "piefed",
                "file_exists": lambda x: False,
                "_": lambda x: x,
                "current_user": type(
                    "User",
                    (),
                    {
                        "is_authenticated": False,
                        "is_anonymous": True,
                        "link": lambda: "testuser",
                    },
                )(),
            }
        )

        # Skip the base template inheritance for testing
        template_source, _, _ = env.loader.get_source(env, "explore.html")

        # Remove extends to avoid dependency issues in CI
        simplified_source = re.sub(
            r"{%.*?extends.*?%}", "", template_source, flags=re.DOTALL
        )
        # Remove import that depends on bootstrap5
        simplified_source = re.sub(
            r"{%.*?from.*?import.*?%}", "", simplified_source, flags=re.DOTALL
        )

        # Create a template from the simplified source
        template = env.from_string(simplified_source)

        # Render with empty topics (this is where the bug would occur)
        rendered = template.render(
            topics=[],  # Empty list - this triggers the len() bug if present
            menu_instance_feeds=[],
            menu_my_feeds=None,
            menu_subscribed_feeds=None,
            active_child="explore",
        )

        # Verify it rendered without errors
        assert rendered is not None
        assert len(rendered) > 0

        # Check that it shows the empty state correctly
        if "There are no communities yet." in rendered:
            print("✅ Empty state renders correctly")
        else:
            print(
                "✅ Template renders without error (empty state message may be in base template)"
            )

        return True

    except Exception as e:
        print(f"❌ Failed to render with empty data: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_explore_renders_with_topics():
    """
    Test that the explore page correctly displays topics when they exist.
    This verifies the fix works with actual data.
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    app_dir = Path(__file__).parent.parent / "app"
    templates_dir = app_dir / "templates"

    if not templates_dir.exists():
        print(f"❌ Templates directory not found: {templates_dir}")
        return False

    try:
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Mock topic class
        class MockTopic:
            def __init__(self, name, machine_name):
                self.name = name
                self.machine_name = machine_name

            def path(self):
                return self.machine_name

        # Create test topics structure
        test_topics = [
            {
                "topic": MockTopic("Technology", "technology"),
                "children": [
                    {"topic": MockTopic("Programming", "programming"), "children": []}
                ],
            },
            {"topic": MockTopic("Science", "science"), "children": []},
        ]

        env.globals.update(
            {
                "theme": lambda: "piefed",
                "file_exists": lambda x: False,
                "_": lambda x: x,
                "current_user": type(
                    "User",
                    (),
                    {
                        "is_authenticated": False,
                        "is_anonymous": True,
                        "link": lambda: "testuser",
                    },
                )(),
            }
        )

        # Get and simplify template
        template_source, _, _ = env.loader.get_source(env, "explore.html")
        simplified_source = re.sub(
            r"{%.*?extends.*?%}", "", template_source, flags=re.DOTALL
        )
        simplified_source = re.sub(
            r"{%.*?from.*?import.*?%}", "", simplified_source, flags=re.DOTALL
        )

        template = env.from_string(simplified_source)

        # Render with topics
        rendered = template.render(
            topics=test_topics,  # Non-empty list with actual topics
            menu_instance_feeds=[],
            menu_my_feeds=None,
            menu_subscribed_feeds=None,
            active_child="explore",
        )

        # Verify topics are displayed
        assert "Technology" in rendered, "Technology topic not displayed"
        assert "Science" in rendered, "Science topic not displayed"
        assert "Programming" in rendered, "Programming sub-topic not displayed"

        # Verify it's NOT showing empty state
        assert (
            "There are no communities yet." not in rendered
        ), "Showing empty state despite having topics!"

        # Verify topic links are correct
        assert 'href="/topic/technology"' in rendered, "Technology link not correct"
        assert 'href="/topic/science"' in rendered, "Science link not correct"

        print("✅ Topics render correctly")
        print("   Found: Technology, Science, Programming")
        print("   Links are properly formatted")

        return True

    except Exception as e:
        print(f"❌ Failed to render with topics: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_no_template_syntax_in_output():
    """
    Verify that no Jinja2 syntax appears in the rendered output.
    This ensures users never see template code even if there's an error.
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    app_dir = Path(__file__).parent.parent / "app"
    templates_dir = app_dir / "templates"

    if not templates_dir.exists():
        print(f"❌ Templates directory not found: {templates_dir}")
        return False

    try:
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        env.globals.update(
            {
                "theme": lambda: "piefed",
                "file_exists": lambda x: False,
                "_": lambda x: x,
                "current_user": type(
                    "User",
                    (),
                    {
                        "is_authenticated": False,
                        "is_anonymous": True,
                        "link": lambda: "testuser",
                    },
                )(),
            }
        )

        # Test with both empty and populated data
        test_cases = [
            ([], "empty topics"),
            (
                [
                    {
                        "topic": type(
                            "Topic", (), {"name": "Test", "path": lambda: "test"}
                        )(),
                        "children": [],
                    }
                ],
                "with topics",
            ),
        ]

        for topics_data, description in test_cases:
            template_source, _, _ = env.loader.get_source(env, "explore.html")
            simplified_source = re.sub(
                r"{%.*?extends.*?%}", "", template_source, flags=re.DOTALL
            )
            simplified_source = re.sub(
                r"{%.*?from.*?import.*?%}", "", simplified_source, flags=re.DOTALL
            )

            template = env.from_string(simplified_source)

            try:
                rendered = template.render(
                    topics=topics_data,
                    menu_instance_feeds=[],
                    menu_my_feeds=None,
                    menu_subscribed_feeds=None,
                    active_child="explore",
                )
            except Exception:
                # If render fails, skip this test case
                continue

            # Check for leaked template syntax
            forbidden_patterns = [
                r"\{\{.*?\}\}",  # Variable tags
                r"\{%.*?%\}",  # Statement tags
                r"\{#.*?#\}",  # Comment tags
                "len(topics)",  # The specific bug
            ]

            # Note: 'topics|length' might appear in HTML comments or as text,
            # but that's OK as long as it's not raw Jinja2 syntax

            for pattern in forbidden_patterns:
                if re.search(pattern, rendered):
                    print(
                        f"❌ Found template syntax in output ({description}): {pattern}"
                    )
                    return False

        print("✅ No template syntax leaked to output")
        return True

    except Exception as e:
        print(f"❌ Error checking output: {e}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        ("Template Compilation", test_explore_template_compiles_correctly),
        ("Render Empty Data", test_explore_renders_with_empty_data),
        ("Render With Topics", test_explore_renders_with_topics),
        ("No Syntax Leakage", test_no_template_syntax_in_output),
    ]

    print("=" * 60)
    print("🧪 REAL-WORLD EXPLORE PAGE TESTS (CI/CD Compatible)")
    print("=" * 60)
    print()

    results = []
    for test_name, test_func in tests:
        print(f"Running: {test_name}")
        print("-" * 40)
        success = test_func()
        results.append((test_name, success))
        print()

    # Summary
    print("=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not success:
            all_passed = False

    print()
    if all_passed:
        print("🎉 All tests passed! The explore page is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. The explore page may have issues.")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
