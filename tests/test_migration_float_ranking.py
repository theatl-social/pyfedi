"""Regression: 544946659eb7 must drop dependent materialized views before it
changes post.ranking's column type.

PostgreSQL refuses to alter a column's type while a view or rule depends on it:

    psycopg2.errors.FeatureNotSupported: cannot alter type of a column used by a
    view or rule
    DETAIL: rule _RETURN on materialized view post_view depends on column "ranking"

Upstream's migration issues a bare `ALTER TABLE post ALTER COLUMN ranking TYPE
FLOAT`. That works upstream, but this fork created a `post_view` materialized
view in e44dfb9a157f and dropped it in 8457362452d9; databases stamped or
restored from a dump predating that drop still carry it, and the bare ALTER
aborts their entire upgrade. Observed in a real deployment on 2026-07-31.

There is no PostgreSQL in the unit-test environment, so these assert the shape of
the migration rather than executing it. The Production Mirror Tests job exercises
the real thing.
"""

import ast
import pathlib

import pytest

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
MIGRATION = VERSIONS / "544946659eb7_float_post_ranking.py"


def _upgrade_source(path):
    src = path.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return ast.get_source_segment(src, node)
    raise AssertionError(f"no upgrade() in {path.name}")


def _code_only(src):
    """Strip comments so assertions match executable code, not the explanation."""
    return "\n".join(
        line for line in src.split("\n") if not line.strip().startswith("#")
    )


def test_drops_dependent_materialized_view():
    code = _code_only(_upgrade_source(MIGRATION))
    assert "DROP MATERIALIZED VIEW" in code, (
        "REGRESSION: 544946659eb7 no longer drops dependent materialized views. "
        "Any database still carrying post_view will fail the whole upgrade with "
        "'cannot alter type of a column used by a view or rule'."
    )


def test_drop_is_idempotent():
    """Must be a no-op on databases that never had the view."""
    code = _code_only(_upgrade_source(MIGRATION))
    assert "IF EXISTS" in code, (
        "REGRESSION: the DROP is not guarded with IF EXISTS, so it will fail on "
        "clean databases that never had post_view."
    )


def test_drop_precedes_the_type_change():
    """Dropping after the ALTER would not help — the ALTER is what fails."""
    code = _code_only(_upgrade_source(MIGRATION))
    assert "DROP MATERIALIZED VIEW" in code and "alter_column" in code
    assert code.index("DROP MATERIALIZED VIEW") < code.index("alter_column"), (
        "REGRESSION: the materialized view is dropped after alter_column; it "
        "must come first or PostgreSQL still refuses the type change."
    )


@pytest.mark.parametrize("column", ["ranking", "ranking_scaled"])
def test_still_converts_both_columns(column):
    """The guard must not have displaced the migration's actual work."""
    code = _code_only(_upgrade_source(MIGRATION))
    assert column in code, f"544946659eb7 no longer converts post.{column}"


def test_no_other_migration_alters_post_column_type_unguarded():
    """Any future migration retyping a post column hits the same wall."""
    offenders = []
    for path in sorted(VERSIONS.glob("*.py")):
        src = path.read_text()
        if "batch_alter_table('post'" not in src and 'batch_alter_table("post"' not in src:
            continue
        try:
            upgrade = _code_only(_upgrade_source(path))
        except AssertionError:
            continue
        if "type_=" not in upgrade:
            continue
        if "DROP MATERIALIZED VIEW" not in upgrade:
            offenders.append(path.name)

    assert not offenders, (
        "These migrations change a column type on `post` without first dropping "
        f"dependent materialized views: {offenders}. PostgreSQL will refuse the "
        "ALTER on any database still carrying post_view."
    )
