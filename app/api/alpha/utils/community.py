from app import cache
from app.api.alpha.views import community_view
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected
from app.community.util import search_for_community
from app.utils import authorise_api_user
from app.models import Community, CommunityMember
from app.shared.community import join_community, leave_community, block_community, unblock_community
from app.utils import communities_banned_from, blocked_instances, blocked_communities

from sqlalchemy import desc, or_


@cache.memoize(timeout=3)
def cached_community_list(type, sort, limit, user_id, query=''):
    if type == 'Subscribed':
        communities = Community.query.filter_by(banned=False).join(CommunityMember).filter(CommunityMember.user_id == user_id)
    elif type == 'Local':
        communities = Community.query.filter_by(ap_id=None, banned=False)
    else:
        communities = Community.query.filter_by(banned=False)

    if user_id:
        banned_from = communities_banned_from(user_id)
        if banned_from:
            communities = communities.filter(Community.id.not_in(banned_from))
        blocked_instance_ids = blocked_instances(user_id)
        if blocked_instance_ids:
            communities = communities.filter(Community.instance_id.not_in(blocked_instance_ids))
        blocked_community_ids = blocked_communities(user_id)
        if blocked_community_ids:
            communities = communities.filter(Community.id.not_in(blocked_community_ids))

    if query:
        communities = communities.filter(or_(Community.title.ilike(f"%{query}%"), Community.ap_id.ilike(f"%{query}%")))

    if sort == 'Active':    # 'Trending Communities' screen
        communities = communities.order_by(desc(Community.last_active)).limit(limit)

    return communities.all()


def get_community_list(auth, data):
    type = data['type_'] if data and 'type_' in data else "All"
    sort = data['sort'] if data and 'sort' in data else "Hot"
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10

    user_id = authorise_api_user(auth) if auth else None

    query = data['q'] if data and 'q' in data else ''
    if user_id and '@' in query and '.' in query and query.startswith('!'):
        search_for_community(query)
        query = query[1:]

    user_id = authorise_api_user(auth) if auth else None

    communities = cached_community_list(type, sort, limit, user_id, query)

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
        raise Exception('missing parameters for community')
    if 'id' in data:
        community = int(data['id'])
    elif 'name' in data:
        community = data['name']

    user_id = authorise_api_user(auth) if auth else None

    try:
        community_json = community_view(community=community, variant=3, stub=False, user_id=user_id)
        return community_json
    except:
        if 'name' in data:
            query = data['name']
            if user_id and '@' in query and '.' in query:
                if not query.startswith('!'):
                    query = '!' + query
                search_for_community(query)
        raise Exception('error - unknown community. Please wait a sec and try again.')


# would be in app/constants.py
SRC_API = 3

def post_community_follow(auth, data):
    required(['community_id', 'follow'], data)
    integer_expected(['community_id'], data)
    boolean_expected(['follow'], data)

    community_id = data['community_id']
    follow = data['follow']

    user_id = join_community(community_id, SRC_API, auth) if follow else leave_community(community_id, SRC_API, auth)
    community_json = community_view(community=community_id, variant=4, stub=False, user_id=user_id)
    return community_json


def post_community_block(auth, data):
    required(['community_id', 'block'], data)
    integer_expected(['community_id'], data)
    boolean_expected(['block'], data)

    community_id = data['community_id']
    block = data['block']

    user_id = block_community(community_id, SRC_API, auth) if block else unblock_community(community_id, SRC_API, auth)
    community_json = community_view(community=community_id, variant=5, user_id=user_id)
    return community_json
