"""
Run database upgrade using Flask-Migrate's programmatic interface.
This calls the migration functions directly without subprocess.
"""

import os

# Set environment variables before importing Flask
os.environ.setdefault("SERVER_NAME", "localhost")
os.environ.setdefault("SECRET_KEY", "your-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///pyfedi.db")
os.environ.setdefault("CACHE_TYPE", "NullCache")


def run_db_upgrade_direct():
    """Run database upgrade using Flask-Migrate directly."""
    try:
        from app import create_app, db
        from flask_migrate import upgrade

        print("🔄 Running database upgrade directly...")

        # Create Flask app
        app = create_app()

        with app.app_context():
            # Run the upgrade
            upgrade()
            print("✅ Database upgrade completed successfully!")
            return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure Flask-Migrate is installed: pip install Flask-Migrate")
        return False
    except Exception as e:
        print(f"❌ Database upgrade error: {e}")
        import traceback

        traceback.print_exc()
        return False


def check_migration_status():
    """Check current migration status."""
    try:
        from app import create_app, db
        from flask_migrate import current, heads

        app = create_app()

        with app.app_context():
            print("📊 Migration Status:")

            # Get current revision
            current_rev = current()
            print(f"   Current revision: {current_rev}")

            # Get head revision(s)
            head_revs = heads()
            print(f"   Head revision(s): {head_revs}")

            if current_rev == head_revs:
                print("   ✅ Database is up to date")
            else:
                print("   ⚠️  Database needs upgrade")

    except Exception as e:
        print(f"❌ Error checking migration status: {e}")


if __name__ == "__main__":
    print("🗄️  FLASK DATABASE UPGRADE (Direct)")
    print("=" * 45)

    # Check status first
    check_migration_status()
    print()

    # Run upgrade
    success = run_db_upgrade_direct()

    if success:
        print("\n📊 Final Status:")
        check_migration_status()
    else:
        print("\n❌ Upgrade failed. See errors above.")
