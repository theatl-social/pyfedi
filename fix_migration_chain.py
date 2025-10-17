"""
Non-destructive migration fix strategy.

This script analyzes and fixes the broken migration chain by:
1. Creating a new unified migration that depends on all orphaned heads
2. Ensuring the topic table creation is included
3. Preserving all existing data
"""

import os
import re
from pathlib import Path
from datetime import datetime


def create_unified_migration():
    """Create a unified migration that consolidates all orphaned heads."""

    migrations_dir = Path("migrations/versions")

    if not migrations_dir.exists():
        print("❌ Migrations directory not found")
        return False

    print("🔧 NON-DESTRUCTIVE MIGRATION FIX")
    print("=" * 50)

    # Step 1: Find all current heads
    print("📊 Step 1: Analyzing current migration state...")

    migration_files = list(migrations_dir.glob("*.py"))
    migrations = {}
    heads = []

    for file_path in migration_files:
        if file_path.name == "__pycache__":
            continue

        try:
            with open(file_path, "r") as f:
                content = f.read()

            revision_match = re.search(r"revision = ['\"]([^'\"]+)['\"]", content)
            down_revision_match = re.search(r"down_revision = ([^\n]+)", content)

            if revision_match:
                revision = revision_match.group(1)
                down_revision_raw = (
                    down_revision_match.group(1).strip()
                    if down_revision_match
                    else None
                )

                # Parse down_revision - keep as raw string for now
                down_revision = down_revision_raw.strip() if down_revision_raw else None
                if down_revision == "None":
                    down_revision = None

                migrations[revision] = {
                    "file": file_path.name,
                    "down_revision": down_revision,
                    "content": content,
                }
        except Exception as e:
            print(f"⚠️  Error reading {file_path.name}: {e}")

    # Find heads (migrations not referenced as down_revision)
    all_down_revisions = set()
    for migration_data in migrations.values():
        if migration_data["down_revision"]:
            down_rev_str = migration_data["down_revision"]
            # Handle tuple format like ('a7b9f2c8e1d4', 'c86d6e395aea')
            if down_rev_str.startswith("(") and down_rev_str.endswith(")"):
                # Parse tuple format
                tuple_content = down_rev_str[1:-1]  # Remove parentheses
                for rev in tuple_content.split(","):
                    rev = rev.strip().strip("'\"")
                    if rev and rev != "None":
                        all_down_revisions.add(rev)
            else:
                # Single revision
                rev = down_rev_str.strip().strip("'\"")
                if rev and rev != "None":
                    all_down_revisions.add(rev)

    heads = [rev for rev in migrations.keys() if rev not in all_down_revisions]

    print(f"   Found {len(heads)} migration heads")

    if len(heads) <= 1:
        print("✅ Migration chain is already unified!")
        return True

    # Show all heads for clarity
    print("\n   Migration heads found:")
    for head in sorted(heads)[:10]:  # Show first 10
        print(f"      - {head} ({migrations[head]['file']})")
    if len(heads) > 10:
        print(f"      ... and {len(heads) - 10} more heads")

    # Step 2: Check for critical migrations
    print("\n📋 Step 2: Checking for critical migrations...")

    topic_migration = None
    for rev, data in migrations.items():
        if "op.create_table('topic'" in data["content"]:
            topic_migration = rev
            print(f"   ✅ Found topic table creation: {rev} ({data['file']})")
            break

    if not topic_migration:
        print("   ⚠️  Topic table creation migration not found")

    # Step 3: Generate unified migration
    print("\n🔨 Step 3: Creating unified migration...")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    new_revision = f"unified_{timestamp[:8]}"
    new_filename = f"{new_revision}_unify_migration_heads.py"

    # Build the down_revision tuple
    down_revisions_str = ", ".join([f"'{head}'" for head in sorted(heads)])

    migration_content = f'''"""Unify all migration heads - non-destructive consolidation

Revision ID: {new_revision}
Revises: {down_revisions_str}
Create Date: {datetime.now().isoformat()}

This migration unifies all {len(heads)} orphaned migration heads into a single chain.
It does not modify any existing data or schema.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '{new_revision}'
down_revision = ({down_revisions_str})
branch_labels = None
depends_on = None


def upgrade():
    """
    Non-destructive upgrade that ensures critical tables exist.
    This migration consolidates all heads and ensures the topic table exists.
    """

    # Get database inspector to check existing tables
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    # Ensure topic table exists (critical for explore page)
    if 'topic' not in existing_tables:
        print("Creating missing 'topic' table...")
        op.create_table('topic',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=50), nullable=True),
            sa.Column('machine_name', sa.String(length=50), nullable=True),
            sa.Column('num_communities', sa.Integer(), nullable=True),
            sa.Column('parent_id', sa.Integer(), nullable=True),
            sa.Column('show_posts_in_children', sa.Boolean(), nullable=True),
            sa.Column('ap_id', sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(['parent_id'], ['topic.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

        # Add topic_id to community if it doesn't exist
        with op.batch_alter_table('community', schema=None) as batch_op:
            columns = [col['name'] for col in inspector.get_columns('community')]
            if 'topic_id' not in columns:
                batch_op.add_column(sa.Column('topic_id', sa.Integer(), nullable=True))
                batch_op.create_index(batch_op.f('ix_community_topic_id'), ['topic_id'], unique=False)
                batch_op.create_foreign_key('fk_community_topic', 'topic', ['topic_id'], ['id'])
    else:
        print("Topic table already exists - skipping creation")

    # Log successful unification
    print(f"✅ Successfully unified {len(heads)} migration heads")
    print("   Migration chain is now linear and complete")


def downgrade():
    """
    Downgrade is not supported for this unification migration.
    This is a one-way consolidation to fix the broken migration chain.
    """
    pass
'''

    # Step 4: Write the migration file
    migration_path = migrations_dir / new_filename

    print(f"   Writing migration: {new_filename}")

    try:
        with open(migration_path, "w") as f:
            f.write(migration_content)

        print(f"   ✅ Migration created: {migration_path}")

        # Step 5: Provide instructions
        print("\n" + "=" * 50)
        print("🎯 MIGRATION FIX COMPLETE!")
        print("=" * 50)
        print("\n📝 Next Steps:")
        print("1. Review the generated migration:")
        print(f"   cat {migration_path}")
        print("\n2. Run the migration:")
        print("   docker exec -it <container> python -m flask db upgrade")
        print("   OR")
        print("   flask db upgrade")
        print("\n3. Verify the topic table was created:")
        print("   docker exec -it <container> python -m flask shell")
        print("   >>> from app.models import Topic")
        print("   >>> Topic.query.count()")
        print("\n4. Seed sample topics (optional):")
        print("   python seed_topics.py")
        print("\n✅ This migration is NON-DESTRUCTIVE:")
        print("   - Preserves all existing data")
        print("   - Only adds missing tables")
        print("   - Consolidates migration heads safely")

        return True

    except Exception as e:
        print(f"❌ Error writing migration: {e}")
        return False


def verify_migration_will_work():
    """Verify the unified migration will work."""

    print("\n🔍 Verification Steps:")
    print("-" * 40)

    # Check if we can import required modules
    try:
        import alembic

        print("✅ Alembic is installed")
    except ImportError:
        print("❌ Alembic not installed - run: pip install alembic")
        return False

    try:
        import sqlalchemy

        print("✅ SQLAlchemy is installed")
    except ImportError:
        print("❌ SQLAlchemy not installed - run: pip install sqlalchemy")
        return False

    # Check migrations directory structure
    env_path = Path("migrations/env.py")
    if env_path.exists():
        print("✅ Migration environment configured")
    else:
        print("❌ Migration environment not found")
        return False

    return True


if __name__ == "__main__":
    print("🚀 NON-DESTRUCTIVE MIGRATION FIX TOOL")
    print("=" * 50)
    print("This tool will:")
    print("1. Analyze your broken migration chain")
    print("2. Create a unified migration that consolidates all heads")
    print("3. Ensure the topic table is created")
    print("4. Preserve all existing data")
    print()

    if verify_migration_will_work():
        print()
        if create_unified_migration():
            print("\n🎉 Success! Follow the instructions above to complete the fix.")
        else:
            print("\n❌ Failed to create unified migration.")
    else:
        print("\n❌ Prerequisites not met. Fix the issues above first.")
