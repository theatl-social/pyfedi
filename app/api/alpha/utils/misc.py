from app.activitypub.util import find_actor_or_create, remote_object_to_json, actor_json_to_model
from app.api.alpha.utils.community import get_community_list
from app.api.alpha.utils.post import get_post_list
from app.api.alpha.utils.user import get_user_list
from app.api.alpha.views import search_view, post_view, reply_view, user_view, community_view
from app.community.util import search_for_community
from app.user.utils import search_for_user
from app.models import Post, PostReply, User, Community, BannedInstances
from app.utils import authorise_api_user

from urllib.parse import urlparse

def get_search(auth, data):
    if not data or ('q' not in data and 'type_' not in data):
        raise Exception('missing parameters for search')

    type = data['type_']
    listing_type = data['listing_type'] if 'listing_type' in data else 'All'

    data['type_'] = listing_type

    search_type = 'Posts' if type == 'Url' else type
    search_json = search_view(search_type)
    if type == 'Communities':
        search_json['communities'] = get_community_list(auth, data)['communities']
    elif type == 'Posts' or type == 'Url':
        search_json['posts'] = get_post_list(auth, data, search_type=type)['posts']
    elif type == 'Users':
        search_json['users'] = get_user_list(auth, data)['users']

    return search_json


def get_resolve_object(auth, data):
    if not data or 'q' not in data:
        raise Exception('missing q parameter for resolve_object')
    user_id = authorise_api_user(auth) if auth else None

    query = data['q']
    object = Post.query.filter_by(ap_id=query).first()
    if object:
        if object.deleted:
            raise Exception('No object found.')
        return post_view(post=object, variant=5, user_id=user_id)
    object = PostReply.query.filter_by(ap_id=query).first()
    if object:
        if object.deleted:
            raise Exception('No object found.')
        return reply_view(reply=object, variant=6, user_id=user_id)
    object = User.query.filter_by(ap_profile_id=query.lower()).first()
    if object:
        if object.deleted or object.banned:
            raise Exception('No object found.')
        return user_view(user=object, variant=7, user_id=user_id)
    object = Community.query.filter_by(ap_profile_id=query.lower()).first()
    if object:
        if object.banned:
            raise Exception('No object found.')
        return community_view(community=object, variant=6, user_id=user_id)

    # if not found and user is logged in, fetch the object if it's not hosted on a banned instance
    # note: accommodating ! and @ queries for communities and people is different from lemmy's v3 api

    if not user_id:   # not logged in
        raise Exception('No object found.')

    server = None
    if query.startswith('https://'):
        parsed_url = urlparse(query)
        server = parsed_url.netloc.lower()
    elif query.startswith('!') or query.startswith('@'):
        address = query[1:]
        if '@' in address:
            name, server = address.lower().split('@')

    if not server:    # can't find server
        raise Exception('No object found.')

    banned = BannedInstances.query.filter_by(domain=server).first()
    if banned:
        raise Exception('No object found.')

    # use hints first in query first
    # assume that queries starting with ! are for a community
    if query.startswith('!'):
        object = search_for_community(query.lower())
        if object:
            return community_view(community=object, variant=6, user_id=user_id)
    # assume that queries starting with @ are for a user
    if query.startswith('@'):
        object = search_for_user(query.lower())
        if object:
            return user_view(user=object, variant=7, user_id=user_id)
    # if the instance is following the lemmy convention, a '/u/' means user and '/c/' means community
    if '/u/' in query or '/c/' in query:
        object = find_actor_or_create(query.lower())
        if object:
            if isinstance(object, User):
                return user_view(user=object, variant=7, user_id=user_id)
            elif isinstance(object, Community):
                return community_view(community=object, variant=6, user_id=user_id)

    # no more hints from query
    ap_json = remote_object_to_json(query)
    if not ap_json:
        raise Exception('No object found.')

    if ('type' in ap_json and
        ap_json['type'] == 'Person' or ap_json['type'] == 'Service' or ap_json['type'] == 'Group' and
        'preferredUsername' in ap_json):
            name = ap_json['preferredUsername'].lower()
            object = actor_json_to_model(ap_json, name, server)
            if object:
                if isinstance(object, User):
                    return user_view(user=object, variant=7, user_id=user_id)
                elif isinstance(object, Community):
                    return community_view(community=object, variant=6, user_id=user_id)


    raise Exception('No object found.')
