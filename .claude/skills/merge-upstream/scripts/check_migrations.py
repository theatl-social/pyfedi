#!/usr/bin/env python3
"""Verify the alembic revision graph without needing a database.

`flask db heads` needs Redis and Postgres because it boots the app. Alembic's
own ScriptDirectory does not -- it only reads migrations/versions/ -- so there
is no reason to fall back on regex-scraping the migration files.

That distinction matters. A regex scrape answers "how many revisions does
nothing point down to", which is a *proxy* for "is the graph healthy". It
cannot see a down_revision naming a revision that does not exist, an orphaned
branch, or what an upgrade from a specific deployed revision would actually
apply. This repo has been burned repeatedly by checks that measured a proxy
instead of the thing (see the "Verify behaviour, never artifacts" section of
SKILL.md), so this one asks alembic directly.

Usage
-----
    uv run python .claude/skills/merge-upstream/scripts/check_migrations.py
    uv run python .claude/skills/merge-upstream/scripts/check_migrations.py --from <revision>

`--from` reports exactly which revisions `flask db upgrade` would apply to a
database currently at that revision -- run it with the head of the previous
release to see what a deploy will do. Find that with:

    git show <previous-release-tag>:migrations/versions/ ...

or read it off the deployed database:

    SELECT version_num FROM alembic_version;

Exit status is 0 when there is exactly one head, 1 otherwise, so it can gate a
merge.
"""

from __future__ import annotations

import argparse
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory


def load_scripts() -> ScriptDirectory:
    cfg = Config("migrations/alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    return ScriptDirectory.from_config(cfg)


def ancestors(script: ScriptDirectory, rev: str) -> set[str]:
    """Every revision reachable by walking down from `rev`, inclusive."""
    seen: set[str] = set()
    stack = [rev]
    while stack:
        current = stack.pop()
        if current is None or current in seen:
            continue
        seen.add(current)
        down = script.get_revision(current).down_revision
        stack.extend(down if isinstance(down, tuple) else [down])
    return seen


def describe(script: ScriptDirectory, rev: str) -> str:
    obj = script.get_revision(rev)
    doc = (obj.doc or "").splitlines()
    return doc[0][:68] if doc else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from",
        dest="from_rev",
        metavar="REVISION",
        help="report what `flask db upgrade` would apply from this revision",
    )
    args = parser.parse_args()

    script = load_scripts()
    heads = script.get_heads()
    bases = script.get_bases()
    total = len({r.revision for r in script.walk_revisions()})

    print(f"Heads: {len(heads)}")
    for head in heads:
        print(f"  {head}  {describe(script, head)}")
    print(f"Bases: {len(bases)}  {bases}")
    print(f"Revisions in graph: {total}")

    if args.from_rev:
        print(f"\n`flask db upgrade` from {args.from_rev} would apply:")
        applied = ancestors(script, heads[0]) - ancestors(script, args.from_rev)
        if not applied:
            print("  (nothing -- already at head)")
        # print in dependency order rather than set order
        for rev in reversed([r.revision for r in script.walk_revisions()]):
            if rev in applied:
                obj = script.get_revision(rev)
                print(f"  {obj.revision:<34} down={obj.down_revision}")
                print(f"      {describe(script, rev)}")
        print(f"\n  {len(applied)} revision(s)")

    if len(heads) != 1:
        print(
            f"\nFAIL: expected exactly 1 head, found {len(heads)}.\n"
            "Create a merge migration whose down_revision is a tuple of every\n"
            "head above -- see step 6 of SKILL.md.",
            file=sys.stderr,
        )
        return 1

    print("\nOK: single head, graph fully connected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
