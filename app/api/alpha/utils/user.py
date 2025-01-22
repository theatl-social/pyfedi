from app.api.alpha.views import user_view
from app.utils import authorise_api_user
from app.api.alpha.utils.post import get_post_list
from app.api.alpha.utils.reply import get_reply_list
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected
from app.models import User
from app.shared.user import block_another_user, unblock_another_user


def get_user(auth, data):
    if not data or ('person_id' not in data and 'username' not in data):
        raise Exception('missing_parameters')

    # user_id = logged in user, person_id = person who's posts, comments etc are being fetched
    # when 'username' is requested, user_id and person_id are the same

    person_id = None
    if 'person_id' in data:
        person_id = int(data['person_id'])

    user_id = None
    if auth:
        user_id = authorise_api_user(auth)
        if 'username' in data:
            data['person_id'] = user_id
            person_id = int(user_id)
        auth = None                 # avoid authenticating user again in get_post_list and get_reply_list

    # bit unusual. have to help construct the json here rather than in views, to avoid circular dependencies
    post_list = get_post_list(auth, data, user_id)
    reply_list = get_reply_list(auth, data, user_id)

    user_json = user_view(user=person_id, variant=3)
    user_json['posts'] = post_list['posts']
    user_json['comments'] = reply_list['comments']
    return user_json


def get_user_list(auth, data):
    # only support 'api/alpha/search?q&type_=Users&sort=TopAll&listing_type=Local&page=1&limit=15' for now
    # (enough for instance view)

    type = data['type_'] if data and 'type_' in data else "All"
    sort = data['sort'] if data and 'sort' in data else "Hot"
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10

    query = data['q'] if data and 'q' in data else ''

    if type == 'Local':
        users = User.query.filter_by(instance_id=1, deleted=False).order_by(User.id)
    else:
        users = User.query.filter_by(deleted=False).order_by(User.id)

    if query:
        users = users.filter(User.user_name.ilike(f"%{query}%"))

    users = users.paginate(page=page, per_page=limit, error_out=False)

    user_list = []
    for user in users:
        user_list.append(user_view(user, variant=2, stub=True))
    list_json = {
        "users": user_list
    }

    return list_json


# would be in app/constants.py
SRC_API = 3

def post_user_block(auth, data):
    required(['person_id', 'block'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['block'], data)

    person_id = data['person_id']
    block = data['block']

    user_id = block_another_user(person_id, SRC_API, auth) if block else unblock_another_user(person_id, SRC_API, auth)
    user_json = user_view(user=person_id, variant=4, user_id=user_id)
    return user_json
