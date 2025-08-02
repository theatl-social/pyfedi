import pytest
from sqlalchemy import desc

from app.models import User, Community


def test_api_instance_blocks(app, session, test_data):
    with app.app_context():
        from app.api.alpha.utils.site import post_site_block
        from app.api.alpha.utils.post import get_post_list

        user_id = 1
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, 'id')
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f'Bearer {jwt}'

        # fail to block instance 1
        data = {"instance_id": 1, "block": True}
        with pytest.raises(Exception) as ex:
            post_site_block(auth, data)
        assert str(ex.value) == 'You cannot block the local instance.'

        high_post_community = Community.query.filter(Community.instance_id != 1).order_by(
            desc(Community.post_count)).first()
        assert high_post_community is not None and hasattr(high_post_community, 'id')

        # post list should be more than 0 before blocking the instance
        data = {"community_id": high_post_community.id}
        response = get_post_list(auth, data)
        assert 'posts' in response and len(response['posts']) > 0

        # block the instance, post list should be 0
        data = {"instance_id": high_post_community.instance_id, "block": True}
        response = post_site_block(auth, data)
        assert 'blocked' in response and response['blocked'] == True
        data = {"community_id": high_post_community.id}
        response = get_post_list(auth, data)
        assert 'posts' in response and len(response['posts']) == 0

        # unblock the instance, post list should go back to more than 0
        data = {"instance_id": high_post_community.instance_id, "block": False}
        response = post_site_block(auth, data)
        assert 'blocked' in response and response['blocked'] == False
        data = {"community_id": high_post_community.id}
        response = get_post_list(auth, data)
        assert 'posts' in response and len(response['posts']) > 0
