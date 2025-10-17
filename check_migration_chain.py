"""
Check if the topic table migration is included in the migration chain.
"""

import os
import re
from pathlib import Path


def analyze_migration_chain():
    """Analyze the migration chain to see if topic table is included."""

    migrations_dir = Path("migrations/versions")

    if not migrations_dir.exists():
        print("❌ Migrations directory not found")
        return

    print("🔍 ANALYZING MIGRATION CHAIN")
    print("=" * 40)

    # Find all migration files
    migration_files = list(migrations_dir.glob("*.py"))
    print(f"📊 Total migration files: {len(migration_files)}")

    # Parse migration dependencies
    migrations = {}
    topic_migrations = []

    for file_path in migration_files:
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Extract revision info
            revision_match = re.search(r"revision = ['\"]([^'\"]+)['\"]", content)
            down_revision_match = re.search(r"down_revision = ([^\\n]+)", content)

            if revision_match:
                revision = revision_match.group(1)
                down_revision = (
                    down_revision_match.group(1).strip()
                    if down_revision_match
                    else None
                )

                # Clean up down_revision
                if down_revision:
                    down_revision = (
                        down_revision.replace("'", "")
                        .replace('"', "")
                        .replace("(", "")
                        .replace(")", "")
                        .strip()
                    )
                    if down_revision == "None":
                        down_revision = None

                migrations[revision] = {
                    "file": file_path.name,
                    "down_revision": down_revision,
                    "content": content,
                }

                # Check if this migration involves topics
                if "topic" in content.lower():
                    topic_migrations.append(
                        {
                            "revision": revision,
                            "file": file_path.name,
                            "down_revision": down_revision,
                        }
                    )

        except Exception as e:
            print(f"⚠️  Error reading {file_path.name}: {e}")

    print(f"\n📋 Topic-related migrations found: {len(topic_migrations)}")
    for tm in topic_migrations:
        print(f"   - {tm['file']} (revision: {tm['revision']})")

        # Check what this migration does with topics
        content = migrations[tm["revision"]]["content"]
        if "create_table.*topic" in content or "op.create_table('topic'" in content:
            print("     ✅ Creates topic table")
        if "topic_id" in content:
            print("     📝 Adds topic_id references")
        if "drop_table.*topic" in content or "op.drop_table('topic'" in content:
            print("     ❌ Drops topic table")

    # Find the current head(s)
    print("\n🎯 Finding migration heads...")

    # Find migrations that are not referenced as down_revision by others
    all_down_revisions = set()
    for migration_data in migrations.values():
        if migration_data["down_revision"]:
            # Handle multiple down_revisions (merge migrations)
            down_revs = migration_data["down_revision"].split(",")
            for down_rev in down_revs:
                down_rev = down_rev.strip()
                if down_rev and down_rev != "None":
                    all_down_revisions.add(down_rev)

    heads = []
    for revision in migrations.keys():
        if revision not in all_down_revisions:
            heads.append(revision)

    print(f"📍 Current migration heads: {len(heads)}")
    for head in heads:
        migration_data = migrations[head]
        print(f"   - {head} ({migration_data['file']})")

    # Check if topic creation is in the chain to the current head
    print("\n🔗 Checking if topic creation is in migration chain...")

    def trace_migration_chain(revision, visited=None):
        """Trace back through migration chain."""
        if visited is None:
            visited = set()

        if revision in visited or revision not in migrations:
            return []

        visited.add(revision)
        chain = [revision]

        migration_data = migrations[revision]
        if migration_data["down_revision"]:
            down_revs = migration_data["down_revision"].split(",")
            for down_rev in down_revs:
                down_rev = down_rev.strip()
                if down_rev and down_rev != "None":
                    chain.extend(trace_migration_chain(down_rev, visited))

        return chain

    # Check if topic creation migration is reachable from current heads
    topic_creation_revisions = []
    for tm in topic_migrations:
        content = migrations[tm["revision"]]["content"]
        if "op.create_table('topic'" in content:
            topic_creation_revisions.append(tm["revision"])

    print(f"📦 Topic table creation migrations: {topic_creation_revisions}")

    for head in heads:
        chain = trace_migration_chain(head)
        has_topic_creation = any(tcr in chain for tcr in topic_creation_revisions)

        print(f"\n📋 Migration chain from head {head}:")
        print(f"   Length: {len(chain)} migrations")
        print(
            f"   Includes topic creation: {'✅ YES' if has_topic_creation else '❌ NO'}"
        )

        if has_topic_creation:
            print("   🎉 Topic table should be created when migrating to this head!")
        else:
            print(
                "   ⚠️  Topic table will NOT be created - this explains the missing table!"
            )


if __name__ == "__main__":
    analyze_migration_chain()
