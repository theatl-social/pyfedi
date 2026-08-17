"""Upstream v1.7.11 smoke test for /api/alpha/post/list.

This is not a unit test: it reads user id 1 and a remote community that already
has posts straight out of whatever database is configured, so it only means
anything against a populated development database. Against CI's SQLite database
it fails with `no such table: user`.

Rather than adding it to the exclusion list in .github/workflows/ci-cd.yml --
which is how ~40 tests, including two security suites, went unrun for months --
it is skipped with a stated reason so the skip is visible in the run output.
Point DATABASE_URL at a populated PostgreSQL database to actually exercise it.
"""

import pytest
from flask import g
from sqlalchemy import desc

from app import create_app
from app.models import User, Community
from config import Config

pytestmark = pytest.mark.skipif(
    Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite"),
    reason=(
        "needs a populated PostgreSQL database (expects user id 1 and a remote "
        "community with posts); cannot run against the SQLite test database"
    ),
)


class TestConfig(Config):
    """Test configuration that inherits from the main Config"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    # Disable real email sending during tests
    MAIL_SUPPRESS_SEND = True


@pytest.fixture
def app():
    """Create and configure a Flask app for testing using the app factory"""
    app = create_app(TestConfig)
    return app


def test_api_post_list(app):
    with app.app_context():
        from app.api.alpha.utils.site import post_site_block
        from app.api.alpha.utils.post import get_post_list

        user_id = 1
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, 'id')
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f'Bearer {jwt}'

        high_post_community = Community.query.filter(Community.instance_id != 1).order_by(
            desc(Community.post_count)).first()
        assert high_post_community is not None and hasattr(high_post_community, 'id')

        # post list should be more than 0
        g.admin_ids = [1]
        data = {"community_id": high_post_community.id}
        response = get_post_list(auth, data)
        assert 'posts' in response and len(response['posts']) > 0


