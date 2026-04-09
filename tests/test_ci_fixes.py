"""Tests for CI fixes: verifying that cached modlist functions were moved correctly.

These tests verify the structural correctness of the refactoring that moved
cached_modlist_for_community and cached_modlist_for_user from
app.api.alpha.views to app.shared.community. They use AST inspection to
avoid triggering the pre-existing circular import chains in the route modules.
"""

import ast
import os
import pytest

os.environ.setdefault("SERVER_NAME", "localhost")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse_file(relative_path):
    """Parse a Python file and return its AST."""
    full_path = os.path.join(PROJECT_ROOT, relative_path)
    with open(full_path) as f:
        return ast.parse(f.read(), filename=relative_path)


def _get_top_level_function_names(tree):
    """Return set of top-level function names defined in an AST."""
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and isinstance(
            next((p for p in ast.walk(tree) if node in getattr(p, "body", [])), None),
            ast.Module,
        )
    }


def _get_function_defs(tree):
    """Return all top-level FunctionDef nodes from an AST module."""
    return [node for node in tree.body if isinstance(node, ast.FunctionDef)]


def _get_import_names(tree):
    """Return all imported names as a set of (module, name) tuples."""
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.add((node.module, alias.name))
    return imports


def test_functions_defined_in_shared_community():
    """cached_modlist_for_community and cached_modlist_for_user must be defined
    in app/shared/community.py."""
    tree = _parse_file("app/shared/community.py")
    func_names = {node.name for node in _get_function_defs(tree)}
    assert (
        "cached_modlist_for_community" in func_names
    ), "cached_modlist_for_community not found as top-level function in app/shared/community.py"
    assert (
        "cached_modlist_for_user" in func_names
    ), "cached_modlist_for_user not found as top-level function in app/shared/community.py"


def test_functions_not_defined_in_views():
    """The functions must NOT be defined in app/api/alpha/views.py anymore
    (they should only be re-exported via import)."""
    tree = _parse_file("app/api/alpha/views.py")
    func_names = {node.name for node in _get_function_defs(tree)}
    assert (
        "cached_modlist_for_community" not in func_names
    ), "cached_modlist_for_community should not be defined in views.py; it should be re-exported"
    assert (
        "cached_modlist_for_user" not in func_names
    ), "cached_modlist_for_user should not be defined in views.py; it should be re-exported"


def test_views_reexports_from_shared():
    """app/api/alpha/views.py must re-export the functions from app.shared.community."""
    tree = _parse_file("app/api/alpha/views.py")
    imports = _get_import_names(tree)
    assert (
        ("app.shared.community", "cached_modlist_for_community") in imports
    ), "views.py must import cached_modlist_for_community from app.shared.community"
    assert (
        ("app.shared.community", "cached_modlist_for_user") in imports
    ), "views.py must import cached_modlist_for_user from app.shared.community"


def test_community_routes_no_views_import():
    """app/community/routes.py must NOT import cached_modlist functions from
    app.api.alpha.views (the old circular dependency)."""
    tree = _parse_file("app/community/routes.py")
    imports = _get_import_names(tree)
    assert (
        ("app.api.alpha.views", "cached_modlist_for_community") not in imports
    ), "community/routes.py should not import cached_modlist_for_community from app.api.alpha.views"
    assert (
        ("app.api.alpha.views", "cached_modlist_for_user") not in imports
    ), "community/routes.py should not import cached_modlist_for_user from app.api.alpha.views"


def test_community_routes_uses_lazy_import():
    """app/community/routes.py must use lazy (in-function) imports of the cached
    modlist functions from app.shared.community, not top-level imports."""
    tree = _parse_file("app/community/routes.py")

    # Check there is no top-level import of these functions
    top_level_imports = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                top_level_imports.add((node.module, alias.name))
    assert (
        ("app.shared.community", "cached_modlist_for_community")
        not in top_level_imports
    ), "cached_modlist_for_community should be lazily imported inside functions, not at top level"

    # Verify the lazy imports exist inside function bodies
    lazy_imports_found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.ImportFrom)
                    and child.module == "app.shared.community"
                ):
                    for alias in child.names:
                        lazy_imports_found.add(alias.name)
    assert (
        "cached_modlist_for_community" in lazy_imports_found
    ), "cached_modlist_for_community should be lazily imported in a function body"
    assert (
        "cached_modlist_for_user" in lazy_imports_found
    ), "cached_modlist_for_user should be lazily imported in a function body"


def test_utils_community_imports_from_shared():
    """app/api/alpha/utils/community.py must import cached_modlist_for_community
    from app.shared.community, not from app.api.alpha.views."""
    tree = _parse_file("app/api/alpha/utils/community.py")
    imports = _get_import_names(tree)
    assert (
        ("app.shared.community", "cached_modlist_for_community") in imports
    ), "utils/community.py must import cached_modlist_for_community from app.shared.community"
    assert (
        ("app.api.alpha.views", "cached_modlist_for_community") not in imports
    ), "utils/community.py should not import cached_modlist_for_community from app.api.alpha.views"


def test_shared_community_no_lazy_imports_from_views():
    """app/shared/community.py must NOT have lazy imports of cached_modlist
    functions from app.api.alpha.views (since they are now defined locally)."""
    tree = _parse_file("app/shared/community.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.api.alpha.views":
            imported_names = {alias.name for alias in node.names}
            assert (
                "cached_modlist_for_community" not in imported_names
            ), "shared/community.py should not lazily import cached_modlist_for_community from views"
            assert (
                "cached_modlist_for_user" not in imported_names
            ), "shared/community.py should not lazily import cached_modlist_for_user from views"


def test_shared_community_functions_use_lazy_view_imports():
    """The moved functions in app/shared/community.py must use lazy imports of
    community_view and user_view from app.api.alpha.views to avoid creating
    a new circular dependency."""
    tree = _parse_file("app/shared/community.py")
    for node in _get_function_defs(tree):
        if node.name in ("cached_modlist_for_community", "cached_modlist_for_user"):
            lazy_imports = set()
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.ImportFrom)
                    and child.module == "app.api.alpha.views"
                ):
                    for alias in child.names:
                        lazy_imports.add(alias.name)
            assert (
                "community_view" in lazy_imports
            ), f"{node.name} must lazily import community_view from app.api.alpha.views"
            assert (
                "user_view" in lazy_imports
            ), f"{node.name} must lazily import user_view from app.api.alpha.views"
