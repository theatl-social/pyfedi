from app import db
from app.api.alpha.views import user_view, reply_view
from app.utils import authorise_api_user
from app.api.alpha.utils.post import get_post_list
from app.api.alpha.utils.reply import get_reply_list
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected
from app.models import Conversation, ChatMessage, Notification, PostReply, User
from app.shared.user import block_another_user, unblock_another_user

from sqlalchemy import text, desc


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
    # lists are empty when viewing own account, to deal with a bug I've yet to identify
    post_list = get_post_list(auth, data, user_id) if not user_id == person_id else {'posts': []}
    reply_list = get_reply_list(auth, data, user_id) if not user_id == person_id else {'comments': []}

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


def get_user_unread_count(auth):
    user_id = authorise_api_user(auth)

    # Mentions are just included in replies

    unread_notifications = db.session.execute(text("SELECT COUNT(id) as c FROM notification WHERE user_id = :user_id AND read = false"), {'user_id': user_id}).scalar()
    unread_messages = db.session.execute(text("SELECT * from chat_message AS cm INNER JOIN conversation c ON cm.conversation_id =c.id WHERE c.read = false AND cm.recipient_id = :user_id"), {'user_id': user_id}).scalar()
    if not unread_messages:
        unread_messages = 0
    if unread_notifications == 0:
        unread_messages = 0

    unread_count = {
        "replies": unread_notifications - unread_messages,
        "mentions": 0,
        "private_messages": unread_messages
    }

    return unread_count


def get_user_replies(auth, data):
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10

    user_id = authorise_api_user(auth)

    unread_urls = db.session.execute(text("select url from notification where user_id = :user_id and read = false and url ilike '%comment%'"), {'user_id': user_id}).scalars()
    unread_ids = []
    for url in unread_urls:
        if '#comment_' in url:                                  # reply format
            unread_ids.append(url.rpartition('_')[-1])
        elif '/comment/' in url:                                # mention format
            unread_ids.append(url.rpartition('/')[-1])

    replies = PostReply.query.filter(PostReply.id.in_(unread_ids)).order_by(desc(PostReply.posted_at)).paginate(page=page, per_page=limit, error_out=False)

    reply_list = []
    for reply in replies:
        reply_list.append(reply_view(reply=reply, variant=5, user_id=user_id))
    list_json = {
        "replies": reply_list
    }

    return list_json


def post_user_mark_all_as_read(auth):
    user_id = authorise_api_user(auth)

    notifications = Notification.query.filter_by(user_id=user_id, read=False)
    for notification in notifications:
        notification.read = True

    conversations = Conversation.query.filter_by(read=False).join(ChatMessage, ChatMessage.conversation_id == Conversation.id).filter_by(recipient_id=user_id)
    for conversation in conversations:
        conversation.read = True

    db.session.commit()

    return {'replies': []}


