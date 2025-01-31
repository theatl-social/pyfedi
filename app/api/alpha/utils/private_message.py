from app import db
from app.api.alpha.views import private_message_view
from app.models import ChatMessage
from app.utils import authorise_api_user

from flask import current_app

from sqlalchemy import text

def get_private_message_list(auth, data):
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10
    unread_only = data['unread_only'] if data and 'unread_only' in data else True

    user_id = authorise_api_user(auth)

    read = not unread_only

    unread_urls = db.session.execute(text("select url from notification where user_id = :user_id and read = false and url ilike '%#message_%'"), {'user_id': user_id}).scalars()
    unread_ids = []
    for url in unread_urls:
        unread_ids.append(url.rpartition('_')[-1])

    private_messages = ChatMessage.query.filter(ChatMessage.recipient_id == user_id, ChatMessage.read == read, ChatMessage.id.in_(unread_ids))
    pm_list = []
    for private_message in private_messages:
        ap_id = 'https://' + current_app.config['SERVER_NAME'] + '/chat/' + str(private_message.conversation_id) + '#message_' +  str(private_message.id)
        pm_list.append(private_message_view(private_message, user_id, ap_id))

    pm_json = {
        "private_messages": pm_list
    }
    return pm_json
