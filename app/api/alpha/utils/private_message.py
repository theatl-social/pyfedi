from sqlalchemy import desc, or_, text

from app import db
from app.api.alpha.utils.validators import required, string_expected, integer_expected, boolean_expected
from app.api.alpha.views import private_message_view
from app.constants import NOTIF_MESSAGE, NOTIF_REPORT
from app.chat.util import send_message, update_message
from app.models import ChatMessage, Conversation, User, Notification, Report, Site
from app.utils import authorise_api_user, markdown_to_html
from app.shared.tasks import task_selector


def get_private_message_list(auth, data):
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10
    unread_only = data['unread_only'] if data and 'unread_only' in data else False

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


def get_private_message_conversation(auth, data):
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10
    if not data or 'person_id' not in data:
        raise Exception('Missing person_id parameter')
    person_id = int(data['person_id'])
    person = User.query.filter_by(id=person_id).one()

    if person is None:
        raise Exception('person not found')

    user_id = authorise_api_user(auth)

    conversation_ids = db.session.execute(text("SELECT conversation_id FROM conversation_member WHERE user_id = :person_id"),
                                         {"person_id": person_id}).scalars()
    pm_list = []
    next_page = None
    if conversation_ids:
        private_messages = ChatMessage.query.filter(ChatMessage.conversation_id.in_(conversation_ids),
                              or_(ChatMessage.recipient_id == user_id,
                                  ChatMessage.sender_id == user_id)).order_by(desc(ChatMessage.created_at))
        private_messages = private_messages.paginate(page=page, per_page=limit, error_out=False)
        for private_message in private_messages:
            pm_list.append(private_message_view(private_message, variant=1))

        next_page = str(private_messages.next_num) if private_messages.next_num else None

    pm_json = {
        "private_messages": pm_list,
        'next_page': next_page
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


def put_private_message(auth, data):
    required(['private_message_id', 'content'], data)
    string_expected(['content'], data)
    integer_expected(['private_message_id'], data)

    chat_message_id = int(data['private_message_id'])
    content = data['content']

    user_id = authorise_api_user(auth)
    # User may only edit own messages
    private_message = ChatMessage.query.filter_by(sender_id=user_id, id=chat_message_id, deleted=False).one()
    private_message.body = content
    private_message.body_html = markdown_to_html(content)
    db.session.commit()

    update_message(private_message)

    return private_message_view(private_message, variant=2)


def post_private_message_delete(auth, data):
    required(['private_message_id', 'deleted'], data)
    boolean_expected(['deleted'], data)
    integer_expected(['private_message_id'], data)

    chat_message_id = int(data['private_message_id'])
    deleted = data['deleted']

    user_id = authorise_api_user(auth)
    private_message = ChatMessage.query.filter_by(sender_id=user_id, id=chat_message_id).one()
    private_message.deleted = deleted
    db.session.commit()

    if deleted:
        task_selector('delete_pm', message_id=private_message.id)
    else:
        task_selector('restore_pm', message_id=private_message.id)

    return private_message_view(private_message, variant=2)


def post_private_message_report(auth, data):
    required(['private_message_id', 'reason'], data)
    integer_expected(['private_message_id'], data)
    string_expected(['reason'], data)

    chat_message_id = data['private_message_id']
    reason = data['reason']

    user_id = authorise_api_user(auth)

    # user may only report received messages
    private_message = ChatMessage.query.filter_by(recipient_id=user_id, id=chat_message_id).one()
    private_message.reported = True

    targets_data = {
            "gen": '0',
            "suspect_conversation_id": private_message.conversation_id,
            "reporter_id": user_id,
            "suspect_message_id": chat_message_id
    }
    report = Report(reasons=reason, description='',
                    type=4, reporter_id=user_id, suspect_conversation_id=private_message.conversation_id,
                    source_instance_id=1,targets=targets_data)
    db.session.add(report)

    already_notified = set()
    for admin in Site.admins():
        if admin.id not in already_notified:
            notify = Notification(title='Reported conversation with user', url='/admin/reports',
                                  user_id=admin.id,
                                  author_id=user_id, notif_type=NOTIF_REPORT,
                                  subtype='chat_conversation_reported',
                                  targets=targets_data)
            db.session.add(notify)
            admin.unread_notifications += 1
    db.session.commit()

    return private_message_view(private_message, variant=3, report=report)

