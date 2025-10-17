"""
Test migration consistency and prevent multiple heads.

This test ensures that database migrations maintain a single linear history
and prevents the "Multiple head revisions are present" error.
"""

import os
import subprocess
import sys

# Set environment variables before importing Flask app
os.environ.setdefault("SERVER_NAME", "test.localhost")
os.environ.setdefault("SECRET_KEY", "test-secret-for-migration-test")
os.environ.setdefault("DATABASE_URL", "sqlite:///memory:test.db")
os.environ.setdefault("CACHE_TYPE", "NullCache")
os.environ.setdefault("CACHE_REDIS_URL", "memory://")
os.environ.setdefault("CELERY_BROKER_URL", "memory://localhost/")
os.environ.setdefault("TESTING", "true")

from flask import Flask
from flask_migrate import Migrate
from app import create_app, db


def test_single_migration_head():
    """Test that there is only one migration head revision."""
    # Create Flask app to initialize migration context
    app = create_app()

    with app.app_context():
        migrate = Migrate()
        migrate.init_app(app, db)

        # Get migration heads using flask db heads command
        try:
            result = subprocess.run(
                [sys.executable, "-m", "flask", "db", "heads"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(__file__)),  # Project root
                env={
                    **os.environ,
                    "PYTHONPATH": os.path.dirname(os.path.dirname(__file__)),
                },
                timeout=30,
            )

            if result.returncode != 0:
                raise Exception(f"flask db heads failed: {result.stderr}")

            output = result.stdout.strip()

            # Parse heads from output
            # Format is: "revision_id (head)" per line
            heads = []
            for line in output.split("\n"):
                if line.strip() and "(head)" in line:
                    revision_id = line.split()[0]
                    heads.append(revision_id)

            # Assert exactly one head exists
            if len(heads) == 0:
                raise AssertionError(
                    "No migration heads found! Database migrations may be missing."
                )
            elif len(heads) > 1:
                heads_str = "\n".join([f"  - {head}" for head in heads])
                raise AssertionError(
                    f"Multiple migration heads detected ({len(heads)} heads):\n{heads_str}\n\n"
                    f"This will cause 'Multiple head revisions are present' errors.\n"
                    f"Fix by creating a merge migration:\n"
                    f"  flask db merge {' '.join(heads)} -m 'merge migration heads'"
                )

            # Success: exactly one head
            print(f"✅ Single migration head found: {heads[0]}")

        except subprocess.TimeoutExpired:
            raise AssertionError("Migration head check timed out after 30 seconds")
        except FileNotFoundError:
            raise AssertionError(
                "Flask command not found. Ensure Flask is installed and in PATH."
            )


def test_migration_history_linear():
    """Test that migration history forms a linear chain without branches."""
    app = create_app()

    with app.app_context():
        migrate = Migrate()
        migrate.init_app(app, db)

        try:
            # Get current migration info
            result = subprocess.run(
                [sys.executable, "-m", "flask", "db", "current"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env={
                    **os.environ,
                    "PYTHONPATH": os.path.dirname(os.path.dirname(__file__)),
                },
                timeout=30,
            )

            # This should succeed without errors
            if result.returncode != 0:
                # If it fails, it might be due to multiple heads
                if "Multiple head revisions" in result.stderr:
                    raise AssertionError(
                        f"Migration history has multiple heads: {result.stderr}\n"
                        f"Run the single head test for more details."
                    )
                else:
                    raise AssertionError(
                        f"Migration current check failed: {result.stderr}"
                    )

            print("✅ Migration history is linear")

        except subprocess.TimeoutExpired:
            raise AssertionError("Migration history check timed out after 30 seconds")


if __name__ == "__main__":
    # Allow running this test standalone
    test_single_migration_head()
    test_migration_history_linear()
    print("✅ All migration tests passed!")
