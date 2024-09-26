from app import cache
from app.utils import authorise_api_user
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected
from app.api.alpha.views import reply_view
from app.models import PostReply
from app.shared.reply import vote_for_reply, bookmark_the_post_reply, remove_the_bookmark_from_post_reply, toggle_post_reply_notification

from sqlalchemy import desc


@cache.memoize(timeout=3)
def cached_reply_list(post_id, person_id, sort, max_depth):
    if post_id:
        replies = PostReply.query.filter(PostReply.deleted == False, PostReply.post_id == post_id, PostReply.depth <= max_depth)
    if person_id:
        replies = PostReply.query.filter_by(deleted=False, user_id=person_id)

    if sort == "Hot":
        replies = replies.order_by(desc(PostReply.ranking)).order_by(desc(PostReply.posted_at))
    elif sort == "Top":
        replies = replies.order_by(desc(PostReply.up_votes - PostReply.down_votes))
    elif sort == "New":
        replies = replies.order_by(desc(PostReply.posted_at))

    return replies.all()


def get_reply_list(auth, data, user_id=None):
    sort = data['sort'] if data and 'sort' in data else "New"
    max_depth = data['max_depth'] if data and 'max_depth' in data else 8
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10
    post_id = data['post_id'] if data and 'post_id' in data else None
    person_id = data['person_id'] if data and 'person_id' in data else None

    if data and not post_id and not person_id:
        raise Exception('missing_parameters')
    else:
        replies = cached_reply_list(post_id, person_id, sort, max_depth)

    if auth:
        try:
            user_id = authorise_api_user(auth)
        except Exception as e:
            raise e

    # user_id: the logged in user
    # person_id: the author of the posts being requested

    start = (page - 1) * limit
    end = start + limit
    replies = replies[start:end]

    replylist = []
    for reply in replies:
        try:
            replylist.append(reply_view(reply=reply, variant=2, user_id=user_id))
        except:
            continue
    list_json = {
        "comments": replylist
    }

    return list_json


# would be in app/constants.py
SRC_API = 3

def post_reply_like(auth, data):
    try:
        required(['comment_id', 'score'], data)
        integer_expected(['comment_id', 'score'], data)
    except:
        raise

    score = data['score']
    reply_id = data['comment_id']
    if score == 1:
        direction = 'upvote'
    elif score == -1:
        direction = 'downvote'
    else:
        score = 0
        direction = 'reversal'

    try:
        user_id = vote_for_reply(reply_id, direction, SRC_API, auth)
        cache.delete_memoized(cached_reply_list)
        reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id, my_vote=score)
        return reply_json
    except:
        raise


def put_reply_save(auth, data):
    try:
        required(['comment_id', 'save'], data)
        integer_expected(['comment_id'], data)
        boolean_expected(['save'], data)
    except:
        raise

    reply_id = data['comment_id']
    save = data['save']

    try:
        if save is True:
            user_id = bookmark_the_post_reply(reply_id, SRC_API, auth)
        else:
            user_id = remove_the_bookmark_from_post_reply(reply_id, SRC_API, auth)
        reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id)
        return reply_json
    except:
        raise


def put_reply_subscribe(auth, data):
    try:
        required(['comment_id', 'subscribe'], data)
        integer_expected(['comment_id'], data)
        boolean_expected(['subscribe'], data)
    except:
        raise

    reply_id = data['comment_id']
    subscribe = data['subscribe']           # not actually processed - is just a toggle

    try:
        user_id = toggle_post_reply_notification(reply_id, SRC_API, auth)
        reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id)
        return reply_json
    except:
        raise
