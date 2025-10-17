"""
Run flask db upgrade using Python subprocess.
This is the most reliable way to execute Flask CLI commands from Python.
"""

import os
import subprocess
import sys

# Set required environment variables
os.environ.setdefault("SERVER_NAME", "localhost")
os.environ.setdefault("SECRET_KEY", "your-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///pyfedi.db")
os.environ.setdefault("CACHE_TYPE", "NullCache")


def run_flask_db_upgrade():
    """Run flask db upgrade command."""
    try:
        print("🔄 Running flask db upgrade...")

        # Method 1: Direct flask command
        result = subprocess.run(
            [sys.executable, "-m", "flask", "db", "upgrade"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),  # Run from script directory
        )

        if result.returncode == 0:
            print("✅ Database upgrade successful!")
            print("STDOUT:", result.stdout)
        else:
            print("❌ Database upgrade failed!")
            print("STDERR:", result.stderr)
            print("STDOUT:", result.stdout)
            return False

        return True

    except Exception as e:
        print(f"❌ Error running flask db upgrade: {e}")
        return False


def alternative_flask_upgrade():
    """Alternative method using flask command directly."""
    try:
        print("🔄 Alternative method: Running flask db upgrade...")

        # Method 2: Using flask executable directly
        result = subprocess.run(
            ["flask", "db", "upgrade"],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            cwd=os.path.dirname(__file__),
        )

        if result.returncode == 0:
            print("✅ Database upgrade successful!")
            print("Output:", result.stdout)
        else:
            print("❌ Database upgrade failed!")
            print("Error:", result.stderr)
            return False

        return True

    except FileNotFoundError:
        print("❌ 'flask' command not found in PATH")
        print("   Try: pip install flask")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("🗄️  FLASK DATABASE UPGRADE")
    print("=" * 40)

    # Try primary method first
    success = run_flask_db_upgrade()

    # If that fails, try alternative
    if not success:
        print("\nTrying alternative method...")
        success = alternative_flask_upgrade()

    if success:
        print("\n🎉 Database is now up to date!")
    else:
        print("\n❌ Failed to upgrade database. Check errors above.")
        sys.exit(1)
