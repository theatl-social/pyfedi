from app.api.alpha.utils.community import get_community_list
from app.api.alpha.utils.post import get_post_list
from app.api.alpha.utils.user import get_user_list
from app.api.alpha.views import search_view, post_view, reply_view, user_view
from app.models import Post, PostReply, User
from app.utils import authorise_api_user


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
        if object.deleted:
            raise Exception('No object found.')
        return user_view(user=object, variant=7, user_id=user_id)

    # TODO: queries for User, and Community
    # Also, if not found and user is logged in, fetch the object
    # probably use remote_object_to_json(uri) in activitypub.util and then create it.

    raise Exception('No object found.')
