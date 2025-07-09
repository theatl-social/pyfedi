from sqlalchemy import desc, or_, text

from app import db
from app.api.alpha.utils.validators import required, string_expected, integer_expected, boolean_expected
from app.api.alpha.views import private_message_view
from app.constants import NOTIF_MESSAGE
from app.chat.util import send_message
from app.models import ChatMessage, Conversation, User, Notification
from app.utils import authorise_api_user


def get_private_message_list(auth, data):
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10
    unread_only = data['unread_only'] if data and 'unread_only' in data else 'true'
    unread_only = True if unread_only == 'true' else False

    user_id = authorise_api_user(auth)

    if unread_only:
        private_messages = ChatMessage.query.filter_by(recipient_id=user_id, read=False).order_by(desc(ChatMessage.created_at))
    else:
        private_messages = ChatMessage.query.filter(or_(ChatMessage.recipient_id == user_id,
                    ChatMessage.sender_id == user_id)).order_by(desc(ChatMessage.created_at))
    private_messages = private_messages.paginate(page=page, per_page=limit, error_out=False)

    pm_list = []
    for private_message in private_messages:
        pm_list.append(private_message_view(private_message, variant=1))

    pm_json = {
        "private_messages": pm_list,
        'next_page': str(private_messages.next_num) if private_messages.next_num else None
    }
    return pm_json


def post_private_message(auth, data):
    required(['content', 'recipient_id'], data)
    string_expected(['content'], data)
    integer_expected(['recipient_id'], data)

    sender = authorise_api_user(auth, return_type='model')
    recipient = User.query.filter_by(id=data['recipient_id']).one()

    existing_conversation = Conversation.find_existing_conversation(recipient=recipient, sender=sender)
    if not existing_conversation:
        existing_conversation = Conversation(user_id=sender.id)
        existing_conversation.members.append(recipient)
        existing_conversation.members.append(sender)
        db.session.add(existing_conversation)
        db.session.commit()

    private_message = send_message(data['content'], existing_conversation.id, user=sender)

    pm_json = private_message_view(private_message, variant=2)
    return pm_json


def post_private_message_mark_as_read(auth, data):
    required(['private_message_id', 'read'], data)
    integer_expected(['private_message_id'], data)
    boolean_expected(['read'], data)

    user = authorise_api_user(auth, return_type='model')
    message_id = data['private_message_id']
    read = data['read']

    private_message = ChatMessage.query.filter_by(id=message_id, recipient_id=user.id).one()
    private_message.read = read

    notif_read = not read
    notifications = Notification.query.filter_by(user_id=user.id, notif_type=NOTIF_MESSAGE, subtype='chat_message', read=notif_read)
    for notification in notifications:
        if 'message_id' in notification.targets and notification.targets['message_id'] == message_id:
            notification.read = read
            if read == True and user.unread_notifications > 0:
                user.unread_notifications -= 1
            elif read == False:
                user.unread_notifications += 1
            break
    db.session.commit()


    return private_message_view(private_message, variant=2)


