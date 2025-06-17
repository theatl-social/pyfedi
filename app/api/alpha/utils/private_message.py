from app.api.alpha.views import private_message_view
from app.models import ChatMessage
from app.utils import authorise_api_user

from flask import current_app
from sqlalchemy import desc

def get_private_message_list(auth, data):
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10
    unread_only = data['unread_only'] if data and 'unread_only' in data else 'true'
    unread_only = True if unread_only == 'true' else False

    user_id = authorise_api_user(auth)

    if unread_only:
        private_messages = ChatMessage.query.filter_by(recipient_id=user_id, read=False).order_by(desc(ChatMessage.created_at))
    else:
        private_messages = ChatMessage.query.filter_by(recipient_id=user_id).order_by(desc(ChatMessage.created_at))
    private_messages = private_messages.paginate(page=page, per_page=limit, error_out=False)

    pm_list = []
    for private_message in private_messages:
        ap_id = 'https://' + current_app.config['SERVER_NAME'] + '/chat/' + str(private_message.conversation_id) + '#message_' +  str(private_message.id)
        pm_list.append(private_message_view(private_message, user_id, ap_id))

    pm_json = {
        "private_messages": pm_list,
        'next_page': str(private_messages.next_num) if private_messages.next_num else None
    }
    return pm_json
