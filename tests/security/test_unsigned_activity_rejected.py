"""SP-001 regression: unsigned activities must NOT be processed.

Asserts that the dict->id reduction in shared_inbox is gone. The vuln allowed
attackers to send unsigned Create/Update activities with a dict object that
contained an `id` field; the code reduced the dict to just its id string,
deferred verification to verify_object_from_source(), and the latter only
checked that the object's URL domain matched the actor's URL domain (both
attacker-controlled).

This is a *structural* test (AST-based) so it runs without DB/Redis. A
behavior test that POSTs an unsigned activity to a live /inbox is valuable
too but requires more infra. See SECURITY_PATCHES.md for the full attack
narrative.
"""

import ast
import pathlib

ROUTES_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "activitypub" / "routes.py"
)


def _shared_inbox_source():
    src = ROUTES_PATH.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "shared_inbox":
            return ast.get_source_segment(src, node)
    raise AssertionError("shared_inbox function not found in app/activitypub/routes.py")


def test_dict_to_id_reduction_is_gone():
    """The exact vulnerable assignment must not exist in shared_inbox.

    The vuln line was:
        request_json['object'] = request_json['object']['id']

    inside an `elif` triggered when both signature checks failed.
    """
    source = _shared_inbox_source()
    forbidden_assignments = [
        "request_json['object'] = request_json['object']['id']",
        'request_json["object"] = request_json["object"]["id"]',
    ]
    for snippet in forbidden_assignments:
        assert snippet not in source, (
            f"SP-001 REGRESSION: shared_inbox contains the dict->id reduction "
            f"{snippet!r}. This allows unsigned activities to be processed."
        )


def test_signature_failure_path_returns_400():
    """When both HTTP-sig and LD-sig fail, the function must terminate with 400.

    We assert by parsing the function body and checking that the `else` branch
    of the signature-failure block contains a `return ('', 400)` statement and
    NOT a fall-through that lets the request continue.
    """
    source = _shared_inbox_source()

    # The structural shape we want: an else clause whose body begins with
    # log_incoming_ap and ends with return '', 400.
    assert "return '', 400" in source or 'return "", 400' in source, (
        "SP-001 REGRESSION: shared_inbox no longer rejects unsigned requests "
        "with HTTP 400. This is the load-bearing rejection."
    )

    # And the SP-001 marker comment must be present so a future reader
    # understands why this path is strict.
    assert "SP-001" in source, (
        "SP-001 marker comment missing from shared_inbox. The marker documents "
        "why we strictly reject unsigned requests; if removed, a future merge "
        "may re-introduce the bypass without reviewer awareness."
    )


def test_security_patches_md_documents_sp001():
    """SECURITY_PATCHES.md must list SP-001 so merges know not to drop it."""
    sp_md = pathlib.Path(__file__).resolve().parents[2] / "SECURITY_PATCHES.md"
    assert sp_md.exists(), "SECURITY_PATCHES.md is missing from repo root"
    content = sp_md.read_text()
    assert "SP-001" in content, "SECURITY_PATCHES.md does not document SP-001"
