"""SP-008 regression: when HttpSignature.precheck fails, shared_inbox must
return 400 immediately. Previously it logged and continued; verify_request
below does not independently re-check date freshness or re-check digest
unless the sender opted to include digest in signed-headers, so a malformed
digest could slip past.
"""

import ast
import pathlib

ROUTES = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "activitypub" / "routes.py"
)


def test_precheck_failure_returns_400():
    src = ROUTES.read_text()
    tree = ast.parse(src)

    # Find shared_inbox; locate the precheck try/except block within it; assert
    # the except body ends with a return statement carrying a 400 status.
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "shared_inbox"):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Try):
                continue
            # Look for HttpSignature.precheck in the try body
            try_src = ast.get_source_segment(src, sub) or ""
            if "HttpSignature.precheck" not in try_src:
                continue
            # Found the right try block. Check each handler.
            for handler in sub.handlers:
                handler_src = ast.get_source_segment(src, handler) or ""
                if "VerificationFormatError" not in handler_src:
                    continue
                assert "return" in handler_src and "400" in handler_src, (
                    "SP-008 REGRESSION: shared_inbox no longer returns 400 "
                    "after precheck failure. Without this, malformed digests "
                    "can slip past since verify_request only conditionally "
                    "re-checks them."
                )
                return
        break
    raise AssertionError(
        "Could not locate the precheck try/except inside shared_inbox; "
        "structure may have changed."
    )
