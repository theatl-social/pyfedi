from app.api.alpha.utils.community import get_community_list
from app.api.alpha.utils.post import get_post_list
from app.api.alpha.utils.user import get_user_list
from app.api.alpha.views import search_view


def get_search(auth, data):
    if not data or ('q' not in data and 'type_' not in data):
        raise Exception('missing_parameters')

    type = data['type_']
    listing_type = data['listing_type'] if 'listing_type' in data else 'Local'

    data['type_'] = listing_type

    search_json = search_view(type)
    if type == 'Communities':
        search_json['communities'] = get_community_list(auth, data)['communities']
    elif type == 'Posts':
        search_json['posts'] = get_post_list(auth, data)['posts']
    elif type == 'Users':
        search_json['users'] = get_user_list(auth, data)['users']

    return search_json

