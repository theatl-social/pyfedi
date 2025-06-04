from app import db
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected, string_expected
from app.api.alpha.views import reply_view, reply_report_view
from app.models import Notification, PostReply, Post
from app.constants import *
from app.shared.reply import vote_for_reply, bookmark_reply, remove_bookmark_reply, subscribe_reply, make_reply, edit_reply, \
                             delete_reply, restore_reply, report_reply, mod_remove_reply, mod_restore_reply
from app.utils import authorise_api_user, blocked_users, blocked_instances

from sqlalchemy import desc, or_, text


def get_reply_list(auth, data, user_id=None):
    sort = data['sort'].lower() if data and 'sort' in data else "new"
    max_depth = data['max_depth'] if data and 'max_depth' in data else None
    page = int(data['page']) if data and 'page' in data else None
    limit = int(data['limit']) if data and 'limit' in data else 10
    post_id = data['post_id'] if data and 'post_id' in data else None
    parent_id = data['parent_id'] if data and 'parent_id' in data else None
    person_id = data['person_id'] if data and 'person_id' in data else None

    if data and not (post_id or parent_id or person_id):
        raise Exception('missing parameters for reply')

    # user_id: the logged in user
    # person_id: the author of the posts being requested

    if auth:
        user_id = authorise_api_user(auth)

    if parent_id and post_id:
        replies = PostReply.query.filter(PostReply.root_id == parent_id, PostReply.post_id == post_id)
        if replies.count() == 0:
            reply_ids = db.session.execute(text('select id from post_reply where :id = ANY(path)'), {"id": parent_id}).scalars()
            replies = PostReply.query.filter(PostReply.id.in_(reply_ids), PostReply.post_id == post_id)
    elif post_id:
        replies = PostReply.query.filter(PostReply.post_id == post_id)
    elif parent_id:
        replies = PostReply.query.filter(PostReply.root_id == parent_id)
        if replies.count() == 0:
            reply_ids = db.session.execute(text('select id from post_reply where :id = ANY(path)'), {"id": parent_id}).scalars()
            replies = PostReply.query.filter(PostReply.id.in_(reply_ids))
    elif person_id:
        replies = PostReply.query.filter_by(user_id=person_id)

    if max_depth:
        replies = replies.filter(PostReply.depth <= max_depth)

    if user_id and user_id != person_id:
        blocked_person_ids = blocked_users(user_id)
        if blocked_person_ids:
            replies = replies.filter(PostReply.user_id.not_in(blocked_person_ids))
        blocked_instance_ids = blocked_instances(user_id)
        if blocked_instance_ids:
            replies = replies.filter(PostReply.instance_id.not_in(blocked_instance_ids))

    if sort == "hot":
        replies = replies.order_by(desc(PostReply.ranking)).order_by(desc(PostReply.posted_at))
    elif sort == "top":
        replies = replies.order_by(desc(PostReply.up_votes - PostReply.down_votes))
    elif sort == "new":
        replies = replies.order_by(desc(PostReply.posted_at))

    if page is not None:
        replies = replies.paginate(page=page, per_page=limit, error_out=False)
    else:
        replies = replies.all()

    replylist = []
    for reply in replies:
        replylist.append(reply_view(reply=reply, variant=2, user_id=user_id))

    list_json = {
        "comments": replylist
    }

    return list_json


def get_reply(auth, data):
    if not data or 'id' not in data:
        raise Exception('missing parameters for comment')

    id = int(data['id'])

    user_id = authorise_api_user(auth) if auth else None

    reply_json = reply_view(reply=id, variant=4, user_id=user_id)
    return reply_json


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
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id, my_vote=score)
    return reply_json


def put_reply_save(auth, data):
    required(['comment_id', 'save'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['save'], data)

    reply_id = data['comment_id']
    save = data['save']

    user_id = bookmark_reply(reply_id, SRC_API, auth) if save else remove_bookmark_reply(reply_id, SRC_API, auth)
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id)
    return reply_json


def put_reply_subscribe(auth, data):
    required(['comment_id', 'subscribe'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['subscribe'], data)

    reply_id = data['comment_id']
    subscribe = data['subscribe']

    user_id = subscribe_reply(reply_id, subscribe, SRC_API, auth)
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id)
    return reply_json


def post_reply(auth, data):
    required(['body', 'post_id'], data)
    string_expected(['body',], data)
    integer_expected(['post_id', 'parent_id', 'language_id'], data)

    body = data['body']
    post_id = data['post_id']
    parent_id = data['parent_id'] if 'parent_id' in data else None
    language_id = data['language_id'] if 'language_id' in data else 2       # FIXME: use site language
    if language_id < 2:
        language_id = 2                                                     # FIXME: use site language

    input = {'body': body, 'notify_author': True, 'language_id': language_id}
    post = Post.query.filter_by(id=post_id).one()

    user_id, reply = make_reply(input, post, parent_id, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def put_reply(auth, data):
    required(['comment_id'], data)
    string_expected(['body',], data)
    integer_expected(['comment_id', 'language_id'], data)
    boolean_expected(['distinguished'], data)

    reply_id = data['comment_id']
    reply = PostReply.query.filter_by(id=reply_id).one()

    body = data['body'] if 'body' in data else reply.body
    language_id = data['language_id'] if 'language_id' in data else reply.language_id
    distinguished = data['distinguished'] if 'distinguished' in data else False
    if language_id < 2:
        language_id = 2                                                     # FIXME: use site language

    input = {'body': body, 'notify_author': True, 'language_id': language_id, 'distinguished': distinguished}
    post = Post.query.filter_by(id=reply.post_id).one()

    user_id, reply = edit_reply(input, reply, post, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def post_reply_delete(auth, data):
    required(['comment_id', 'deleted'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['deleted'], data)

    reply_id = data['comment_id']
    deleted = data['deleted']

    if deleted == True:
        user_id, reply = delete_reply(reply_id, SRC_API, auth)
    else:
        user_id, reply = restore_reply(reply_id, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def post_reply_report(auth, data):
    required(['comment_id', 'reason'], data)
    integer_expected(['comment_id'], data)
    string_expected(['reason'], data)

    reply_id = data['comment_id']
    reason = data['reason']
    input = {'reason': reason, 'description': '', 'report_remote': True}

    user_id, report = report_reply(reply_id, input, SRC_API, auth)

    reply_json = reply_report_view(report=report, reply_id=reply_id, user_id=user_id)
    return reply_json


def post_reply_remove(auth, data):
    required(['comment_id', 'removed'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['removed'], data)
    string_expected(['reason'], data)

    reply_id = data['comment_id']
    removed = data['removed']

    if removed == True:
        reason = data['reason'] if 'reason' in data else 'Removed by mod'
        user_id, reply = mod_remove_reply(reply_id, reason, SRC_API, auth)
    else:
        reason = data['reason'] if 'reason' in data else 'Restored by mod'
        user_id, reply = mod_restore_reply(reply_id, reason, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def post_reply_mark_as_read(auth, data):
    required(['comment_reply_id', 'read'], data)
    integer_expected(['comment_reply_id'], data)
    boolean_expected(['read'], data)

    reply_id = data['comment_reply_id']
    read = data['read']

    user_id = authorise_api_user(auth)

    # no real support for this. Just marking the Notification for the reply really
    # notification has its own id, which would be handy, but reply_view is currently just returning the reply.id for that
    reply = PostReply.query.filter_by(id=reply_id).one()

    reply_url = '#comment_' + str(reply.id)
    mention_url = '/comment/' + str(reply.id)
    notification = Notification.query.filter(Notification.user_id == user_id, or_(Notification.url.ilike(f"%{reply_url}%"), Notification.url.ilike(f"%{mention_url}%"))).first()
    if notification:
        notification.read = read
        db.session.commit()

    reply_json = {'comment_reply_view': reply_view(reply=reply, variant=5, user_id=user_id, read=True)}
    return reply_json





