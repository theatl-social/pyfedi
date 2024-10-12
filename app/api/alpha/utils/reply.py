from app import cache
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected, string_expected
from app.api.alpha.views import reply_view
from app.models import PostReply, Post
from app.shared.reply import vote_for_reply, bookmark_the_post_reply, remove_the_bookmark_from_post_reply, toggle_post_reply_notification, make_reply, edit_reply
from app.utils import authorise_api_user, blocked_users, blocked_instances

from sqlalchemy import desc

# person_id param: the author of the reply; user_id param: the current logged-in user
@cache.memoize(timeout=3)
def cached_reply_list(post_id, person_id, sort, max_depth, user_id):
    if post_id:
        replies = PostReply.query.filter(PostReply.deleted == False, PostReply.post_id == post_id, PostReply.depth <= max_depth)
    if person_id:
        replies = PostReply.query.filter_by(deleted=False, user_id=person_id)

    if user_id is not None:
        blocked_person_ids = blocked_users(user_id)
        if blocked_person_ids:
            replies = replies.filter(PostReply.user_id.not_in(blocked_person_ids))
        blocked_instance_ids = blocked_instances(user_id)
        if blocked_instance_ids:
            replies = replies.filter(PostReply.instance_id.not_in(blocked_instance_ids))

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
        if auth:
            user_id = authorise_api_user(auth)
        replies = cached_reply_list(post_id, person_id, sort, max_depth, user_id)

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
    required(['comment_id', 'score'], data)
    integer_expected(['comment_id', 'score'], data)

    score = data['score']
    reply_id = data['comment_id']
    if score == 1:
        direction = 'upvote'
    elif score == -1:
        direction = 'downvote'
    else:
        score = 0
        direction = 'reversal'

    user_id = vote_for_reply(reply_id, direction, SRC_API, auth)
    cache.delete_memoized(cached_reply_list)
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id, my_vote=score)
    return reply_json


def put_reply_save(auth, data):
    required(['comment_id', 'save'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['save'], data)

    reply_id = data['comment_id']
    save = data['save']

    user_id = bookmark_the_post_reply(reply_id, SRC_API, auth) if save else remove_the_bookmark_from_post_reply(reply_id, SRC_API, auth)
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id)
    return reply_json


def put_reply_subscribe(auth, data):
    required(['comment_id', 'subscribe'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['subscribe'], data)

    reply_id = data['comment_id']
    subscribe = data['subscribe']           # not actually processed - is just a toggle

    user_id = toggle_post_reply_notification(reply_id, SRC_API, auth)
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id)
    return reply_json


def post_reply(auth, data):
    required(['body', 'post_id'], data)
    string_expected(['body',], data)
    integer_expected(['post_id', 'parent_id', 'language_id'], data)

    body = data['body']
    post_id = data['post_id']
    parent_id = data['parent_id'] if 'parent_id' in data else None
    language_id = data['language_id'] if 'language_id' in data else 2

    input = {'body': body, 'notify_author': True, 'language_id': language_id}
    post = Post.query.get(post_id)
    if not post:
        raise Exception('parent_not_found')

    user_id, reply = make_reply(input, post, parent_id, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def put_reply(auth, data):
    required(['comment_id'], data)
    string_expected(['body',], data)
    integer_expected(['comment_id', 'language_id'], data)

    reply_id = data['comment_id']
    body = data['body'] if 'body' in data else ''
    language_id = data['language_id'] if 'language_id' in data else 2

    input = {'body': body, 'notify_author': True, 'language_id': language_id}
    reply = PostReply.query.get(reply_id)
    if not reply:
        raise Exception('reply_not_found')
    post = Post.query.get(reply.post_id)
    if not post:
        raise Exception('post_not_found')

    user_id, reply = edit_reply(input, reply, post, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json
