from app.api.alpha.views import user_view
from app.utils import authorise_api_user
from app.api.alpha.utils.post import get_post_list
from app.api.alpha.utils.reply import get_reply_list


def get_user(auth, data):
    if not data or ('person_id' not in data and 'username' not in data):
        raise Exception('missing_parameters')

    person_id = int(data['person_id'])           # TODO: handle 'username' (was passed on login, as a way to get subscription list, but temporarily removed)

    user_id = None
    if auth:
        try:
            user_id = authorise_api_user(auth)
            auth = None
        except Exception as e:
            raise e

    # user_id = logged in user, person_id = person who's posts, comments etc are being fetched

    # bit unusual. have to help construct the json here rather than in views, to avoid circular dependencies
    post_list = get_post_list(auth, data, user_id)
    reply_list = get_reply_list(auth, data, user_id)

    try:
        user_json = user_view(user=person_id, variant=3)
        user_json['posts'] = post_list['posts']
        user_json['comments'] = reply_list['comments']
        return user_json
    except:
        raise



