"""Regression tests for the image-upload quota bug fix and the v1.7.0 merge grafts.

Covers:
- FILE_UPLOAD_QUOTA default raised to 1 GB (config.py)
- favorite_communities() graft: new function, @cache.memoize restored, CommunityFavorite import
- can_upload_video(user=...) signature graft (upstream video-upload change)
- the exact upload error-code strings that app/static/js/media_library.js maps

These guard the seam where our fork-reformatted code met upstream's v1.7.0 changes.
"""

import io
import os
import pathlib

import pytest
from werkzeug.datastructures import FileStorage

# Import app before config to avoid the config<->app circular import.
from app import create_app, db
from config import Config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    CACHE_TYPE = "NullCache"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SERVER_NAME = "test.localhost"
    RATELIMIT_ENABLED = False
    CELERY_ALWAYS_EAGER = True


@pytest.fixture
def app():
    application = create_app(_TestConfig)
    with application.app_context():
        try:
            db.create_all()
        except Exception as e:  # tolerate Postgres-only DDL on SQLite
            if "parse_websearch" not in str(e) and "CREATE OR REPLACE" not in str(e):
                raise
        yield application
        db.session.remove()
        db.drop_all()


# --- FILE_UPLOAD_QUOTA -------------------------------------------------------

def test_file_upload_quota_default_literal_is_1gb():
    # Assert the source default so the test is immune to a FILE_UPLOAD_QUOTA env
    # var being set in CI. 1073741824 == 1 GiB.
    src = (REPO_ROOT / "config.py").read_text()
    assert "1073741824" in src, "FILE_UPLOAD_QUOTA default should be 1 GB (1073741824)"


def test_file_upload_quota_config_value():
    expected = int(os.environ.get("FILE_UPLOAD_QUOTA") or 1073741824)
    assert Config.FILE_UPLOAD_QUOTA == expected


# --- favorite_communities() graft -------------------------------------------

def test_favorite_communities_is_memoized():
    # The graft initially dropped @cache.memoize(timeout=300); flask-caching adds
    # an .uncached attribute to memoized functions. Without it, hot-path callers
    # re-query every render and cache.delete_memoized(...) becomes a silent no-op.
    from app.utils import favorite_communities

    assert hasattr(favorite_communities, "uncached"), (
        "favorite_communities must be @cache.memoize'd"
    )


def test_favorite_communities_none_returns_empty(app):
    from app.utils import favorite_communities

    with app.app_context():
        assert favorite_communities(None) == []


def test_favorite_communities_returns_ids(app):
    from app.models import CommunityFavorite
    from app.utils import favorite_communities

    with app.app_context():
        # PieFed's full db.create_all() doesn't complete on SQLite (Postgres-only
        # DDL), so create just the table this test needs.
        CommunityFavorite.__table__.create(db.engine, checkfirst=True)
        db.session.add(CommunityFavorite(user_id=1, community_id=42))
        db.session.add(CommunityFavorite(user_id=1, community_id=99))
        db.session.add(CommunityFavorite(user_id=2, community_id=7))
        db.session.commit()

        assert sorted(favorite_communities(1)) == [42, 99]
        assert favorite_communities(2) == [7]
        assert favorite_communities(3) == []


# --- can_upload_video(user=...) signature graft ------------------------------

def test_can_upload_video_accepts_user_kwarg(app, monkeypatch):
    # Upstream changed can_upload_video() -> can_upload_video(user=None); our
    # fork's reformatted no-arg version had to be re-grafted so that
    # shared/upload.py's `can_upload_video(user)` call works.
    import app.utils as u

    monkeypatch.setattr(u, "get_setting", lambda *a, **k: "no")
    with app.app_context():
        # 'no' -> False, but the call must accept the user kwarg without TypeError.
        assert u.can_upload_video(user=None) is False


def test_can_upload_video_uses_passed_user(app, monkeypatch):
    import app.utils as u

    monkeypatch.setattr(u, "get_setting", lambda *a, **k: "admins")

    class _Admin:
        def get_id(self):
            return 9

        def is_admin_or_staff(self):
            return True

        is_authenticated = True

    class _NonAdmin:
        def get_id(self):
            return 9

        def is_admin_or_staff(self):
            return False

        is_authenticated = True

    with app.app_context():
        # The PASSED user (not current_user) must decide the outcome.
        assert u.can_upload_video(user=_Admin()) is True
        assert u.can_upload_video(user=_NonAdmin()) is False


# --- upload error-code contract ---------------------------------------------
# media_library.js maps these exact strings to friendly messages. If the Python
# side renames a code without updating the JS, uploads silently show the generic
# "Upload failed" again. These tests lock the contract.

def test_process_upload_rejects_missing_file(app):
    from app.shared.upload import process_upload

    with app.app_context():
        with pytest.raises(Exception, match="file not uploaded"):
            process_upload(None)


def test_process_upload_rejects_disallowed_filetype(app):
    from app.shared.upload import process_upload

    bad = FileStorage(stream=io.BytesIO(b"x"), filename="evil.exe")
    with app.app_context():
        with pytest.raises(Exception, match="filetype not allowed"):
            process_upload(bad)


def test_quota_exceeded_code_matches_js_map():
    api_src = (REPO_ROOT / "app" / "api" / "alpha" / "utils" / "upload.py").read_text()
    js_src = (REPO_ROOT / "app" / "static" / "js" / "media_library.js").read_text()

    # API raises this exact string; the error handler forwards str(e) as `message`.
    assert "quota_exceeded" in api_src
    # media_library.js must map every code it can receive.
    for code in ["quota_exceeded", "incorrect_login", "filetype not allowed",
                 "file not uploaded", "rate_limited"]:
        assert code in js_src, f"media_library.js no longer maps '{code}'"
