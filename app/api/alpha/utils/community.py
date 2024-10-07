from app import cache
from app.api.alpha.views import community_view
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected
from app.utils import authorise_api_user
from app.models import Community, CommunityMember
from app.shared.community import join_community, leave_community, block_community, unblock_community
from app.utils import communities_banned_from


@cache.memoize(timeout=3)
def cached_community_list(type, user_id):
    if type == 'Subscribed' and user_id is not None:
        communities = Community.query.filter_by(banned=False).join(CommunityMember).filter(CommunityMember.user_id == user_id)
        banned_from = communities_banned_from(user_id)
        if banned_from:
            communities = communities.filter(Community.id.not_in(banned_from))
    else:
        communities = Community.query.filter_by(banned=False)

    return communities.all()


def get_community_list(auth, data):
    type = data['type_'] if data and 'type_' in data else "All"
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10

    if auth:
        try:
            user_id = authorise_api_user(auth)
        except:
            raise
    else:
        user_id = None

    communities = cached_community_list(type, user_id)

    start = (page - 1) * limit
    end = start + limit
    communities = communities[start:end]

    communitylist = []
    for community in communities:
        communitylist.append(community_view(community=community, variant=2, stub=True, user_id=user_id))
    list_json = {
        "communities": communitylist
    }

    return list_json


def get_community(auth, data):
    if not data or ('id' not in data and 'name' not in data):
        raise Exception('missing_parameters')
    if 'id' in data:
        community = int(data['id'])
    elif 'name' in data:
        community = data['name']

    if auth:
        try:
            user_id = authorise_api_user(auth)
        except:
            raise
    else:
        user_id = None

    try:
        community_json = community_view(community=community, variant=3, stub=False, user_id=user_id)
        return community_json
    except:
        raise


# would be in app/constants.py
SRC_API = 3

def post_community_follow(auth, data):
    try:
        required(['community_id', 'follow'], data)
        integer_expected(['community_id'], data)
        boolean_expected(['follow'], data)
    except:
        raise

    community_id = data['community_id']
    follow = data['follow']

    if auth:
        try:
            user_id = authorise_api_user(auth)
        except:
            raise
    else:
        user_id = None

    try:
        if follow == True:
            user_id = join_community(community_id, SRC_API, auth)
        else:
            user_id = leave_community(community_id, SRC_API, auth)
        community_json = community_view(community=community_id, variant=4, stub=False, user_id=user_id)
        return community_json
    except:
        raise


def post_community_block(auth, data):
    try:
        required(['community_id', 'block'], data)
        integer_expected(['community_id'], data)
        boolean_expected(['block'], data)
    except:
        raise

    community_id = data['community_id']
    block = data['block']

    try:
        if block == True:
            user_id = block_community(community_id, SRC_API, auth)
        else:
            user_id = unblock_community(community_id, SRC_API, auth)
        community_json = community_view(community=community_id, variant=5, user_id=user_id)
        return community_json
    except:
        raise
