import pytest
from flask import g

from app.models import Site, User


def test_api_get_site(app, session, test_site, test_data):
    with app.app_context():
        with app.test_request_context():
            from app.api.alpha.utils.site import get_site

            anon_response = get_site(None)
            assert anon_response is not None and 'version' in anon_response
            assert 'my_user' not in anon_response

            user_id = 1
            user = User.query.get(user_id)
            assert user is not None and hasattr(user, 'id')
            jwt = user.encode_jwt_token()
            assert jwt is not None
            auth = f'Bearer {jwt}'

            logged_in_response = get_site(auth)
            assert logged_in_response is not None and 'version' in logged_in_response
            assert 'my_user' in logged_in_response
            assert logged_in_response['my_user']['local_user_view'][
                       'show_read_posts'] == False if user.hide_read_posts == True else True
