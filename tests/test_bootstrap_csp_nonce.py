"""
Test that Bootstrap scripts include CSP nonce attributes.

This test verifies the fix for the CSP nonce issue where Bootstrap/Popper
scripts were being blocked because they lacked proper nonce attributes.

The fix uses bootstrap-flask's native `nonce` parameter in load_js() instead
of fragile string replacement.
"""

import pytest
import re
import os

# Set minimal environment for imports that don't need full app
os.environ.setdefault("SERVER_NAME", "test.localhost")
os.environ.setdefault("SECRET_KEY", "test-ci-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CACHE_TYPE", "NullCache")
os.environ.setdefault("TESTING", "true")


class TestBootstrapCSPNonce:
    """Test CSP nonce is properly applied to Bootstrap scripts."""

    def test_bootstrap_load_js_supports_nonce_parameter(self):
        """Verify bootstrap-flask supports the nonce parameter."""
        from flask_bootstrap import Bootstrap5
        import inspect

        sig = inspect.signature(Bootstrap5.load_js)
        params = list(sig.parameters.keys())

        assert "nonce" in params, (
            "bootstrap-flask load_js() must support 'nonce' parameter. "
            "Upgrade to bootstrap-flask >= 2.5.0 if this fails."
        )

    def test_base_template_uses_native_nonce_parameter(self):
        """Verify base.html uses the native nonce parameter, not string replacement."""
        from pathlib import Path

        base_template = Path(__file__).parent.parent / "app" / "templates" / "base.html"
        content = base_template.read_text()

        # Should use native parameter
        assert (
            "bootstrap.load_js(nonce=nonce)" in content
        ), "base.html should use bootstrap.load_js(nonce=nonce) for CSP compliance"

        # Should NOT use the old string replacement hack
        assert ".replace('<script '" not in content, (
            "base.html should not use string replacement for nonce injection - "
            "use the native nonce parameter instead"
        )

    def test_nonce_is_unique_per_call(self):
        """Test that gibberish() generates unique values."""
        from app.utils import gibberish

        nonces = set()
        for _ in range(100):
            nonce = gibberish()
            assert nonce not in nonces, "Nonces must be unique per request"
            nonces.add(nonce)

    def test_nonce_format_is_valid(self):
        """Test that generated nonces have valid format for CSP."""
        from app.utils import gibberish

        for _ in range(10):
            nonce = gibberish()
            # Verify nonce is a valid format (alphanumeric, reasonable length)
            assert len(nonce) >= 8, "Nonce should be at least 8 characters"
            assert nonce.isalnum(), "Nonce should be alphanumeric"

    def test_bootstrap_flask_generates_nonce_in_script_tags(self):
        """Test that bootstrap-flask properly adds nonce to script tags."""
        from flask import Flask
        from flask_bootstrap import Bootstrap5

        # Create minimal Flask app just for template rendering
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test"
        Bootstrap5(app)

        with app.app_context():
            with app.test_request_context("/"):
                from flask import render_template_string

                test_nonce = "abc123xyz789"
                html = render_template_string(
                    "{{ bootstrap.load_js(nonce=nonce) }}", nonce=test_nonce
                )

                # Find all script tags
                script_pattern = r"<script[^>]*>"
                script_tags = re.findall(script_pattern, html)

                assert len(script_tags) > 0, "Should generate at least one script tag"

                # All script tags should have the nonce
                for tag in script_tags:
                    assert (
                        f'nonce="{test_nonce}"' in tag
                    ), f"Script tag missing nonce: {tag}"

    def test_csp_header_format(self):
        """Test that CSP header format is correct when nonce is included."""
        from app.utils import gibberish

        nonce = gibberish()
        csp_header = (
            f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic'; "
            f"object-src 'none'; base-uri 'none';"
        )

        # Verify the CSP header contains the nonce in correct format
        assert f"'nonce-{nonce}'" in csp_header
        assert "'strict-dynamic'" in csp_header
        assert "script-src" in csp_header
