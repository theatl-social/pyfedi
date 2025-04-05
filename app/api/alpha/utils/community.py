from app.api.alpha.views import community_view
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected, string_expected, array_of_integers_expected
from app.community.util import search_for_community
from app.utils import authorise_api_user
from app.constants import *
from app.models import Community, CommunityMember
from app.shared.community import join_community, leave_community, block_community, unblock_community, make_community, edit_community, subscribe_community, delete_community, restore_community
from app.utils import communities_banned_from, blocked_instances, blocked_communities

from sqlalchemy import desc, or_


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

    if sort == 'New':
        communities = communities.order_by(desc(Community.created_at))
    else:
        communities = communities.order_by(desc(Community.last_active))

    communities = communities.paginate(page=page, per_page=limit, error_out=False)

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


def post_community(auth, data):
    required(['name', 'title'], data)
    string_expected(['name', 'title', 'description', 'rules', 'icon_url', 'banner_url'], data)
    boolean_expected(['nsfw', 'restricted_to_mods', 'local_only'], data)
    array_of_integers_expected(['discussion_languages'], data)

    name = data['name']
    title = data['title']
    description = data['description'] if 'description' in data else ''
    rules = data['rules'] if 'rules' in data else ''
    icon_url = data['icon_url'] if 'icon_url' in data else None
    banner_url = data['banner_url'] if 'banner_url' in data else None
    nsfw = data['nsfw'] if 'nsfw' in data else False
    restricted_to_mods = data['restricted_to_mods'] if 'restricted_to_mods' in data else False
    local_only = data['local_only'] if 'local_only' in data else False
    discussion_languages = data['discussion_languages'] if 'discussion_languages' in data else [2]  # FIXME: use site language

    input = {'name': name, 'title': title, 'description': description, 'rules': rules,
             'icon_url': icon_url, 'banner_url': banner_url,
             'nsfw': nsfw, 'restricted_to_mods': restricted_to_mods, 'local_only': local_only,
             'discussion_languages': discussion_languages}

    user_id, community_id = make_community(input, SRC_API, auth)
    community_json = community_view(community=community_id, variant=4, user_id=user_id)
    return community_json


def put_community(auth, data):
    required(['community_id'], data)
    integer_expected(['community_id'], data)
    string_expected(['title', 'description', 'rules', 'icon_url', 'banner_url'], data)
    boolean_expected(['nsfw', 'restricted_to_mods', 'local_only'], data)
    array_of_integers_expected(['discussion_languages'], data)

    community_id = data['community_id']
    community = Community.query.filter_by(id=community_id).one()

    title = data['title'] if 'title' in data else community.title
    description = data['description'] if 'description' in data else community.description
    rules = data['rules'] if 'rules' in data else community.rules
    if 'icon_url' in data:
        icon_url = data['icon_url']
    elif community.icon_id:
        icon_url = community.icon.medium_url()
    else:
        icon_url = None
    if 'banner_url' in data:
        banner_url = data['banner_url']
    elif community.image_id:
        banner_url = community.image.medium_url()
    else:
        banner_url = None
    nsfw = data['nsfw'] if 'nsfw' in data else community.nsfw
    restricted_to_mods = data['restricted_to_mods'] if 'restricted_to_mods' in data else community.restricted_to_mods
    local_only = data['local_only'] if 'local_only' in data else community.local_only
    if 'discussion_languages' in data:
        discussion_languages = data['discussion_languages']
    else:
        discussion_languages = []
        for cm in community.languages:
            discussion_languages.append(cm.id)

    input = {'community_id': community_id, 'title': title, 'description': description, 'rules': rules,
             'icon_url': icon_url, 'banner_url': banner_url,
             'nsfw': nsfw, 'restricted_to_mods': restricted_to_mods, 'local_only': local_only,
             'discussion_languages': discussion_languages}

    user_id = edit_community(input, community, SRC_API, auth)
    community_json = community_view(community=community, variant=4, user_id=user_id)
    return community_json


def put_community_subscribe(auth, data):
    required(['community_id', 'subscribe'], data)
    integer_expected(['community_id'], data)
    boolean_expected(['subscribe'], data)

    community_id = data['community_id']
    subscribe = data['subscribe']

    user_id = subscribe_community(community_id, subscribe, SRC_API, auth)
    community_json = community_view(community=community_id, variant=4, user_id=user_id)
    return community_json


def post_community_delete(auth, data):
    required(['community_id', 'deleted'], data)
    integer_expected(['community_id'], data)
    boolean_expected(['deleted'], data)

    community_id = data['community_id']
    deleted = data['deleted']

    if deleted:
        user_id = delete_community(community_id, SRC_API, auth)
    else:
        user_id = restore_community(community_id, SRC_API, auth)
    community_json = community_view(community=community_id, variant=4, user_id=user_id)
    return community_json
