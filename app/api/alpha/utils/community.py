from app import cache
from app.api.alpha.views import community_view
from app.utils import authorise_api_user
from app.models import Community, CommunityMember
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
        except Exception as e:
            raise e
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

    try:
        community_json = community_view(community=community, variant=3)
        return community_json
    except:
        raise
