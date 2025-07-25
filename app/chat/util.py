from flask import flash, current_app
from flask_babel import _
from flask_login import current_user

from app import db
from app.activitypub.signature import send_post_request
from app.constants import NOTIF_MESSAGE
from app.models import User, ChatMessage, Notification, utcnow, Conversation
from app.utils import shorten_string, gibberish, markdown_to_html


def send_message(message: str, conversation_id: int, user: User = current_user) -> ChatMessage:
    conversation = Conversation.query.get(conversation_id)
    reply = ChatMessage(sender_id=user.id, conversation_id=conversation.id,
                        body=message, body_html=markdown_to_html(message))
    conversation.updated_at = utcnow()
    db.session.add(reply)
    db.session.commit()
    for recipient in conversation.members:
        if recipient.id != user.id:
            reply.recipient_id = recipient.id
            reply.ap_id = f"https://{current_app.config['SERVER_NAME']}/private_message/{reply.id}"
            db.session.commit()
            if recipient.is_local():
                # Notify local recipient
                targets_data = {'gen': '0', 'conversation_id': conversation.id, 'message_id': reply.id}
                notify = Notification(title=shorten_string('New message from ' + user.display_name()),
                                      url=f'/chat/{conversation_id}#message_{reply.id}',
                                      user_id=recipient.id,
                                      author_id=user.id,
                                      notif_type=NOTIF_MESSAGE,
                                      subtype='chat_message',
                                      targets=targets_data)
                db.session.add(notify)
                recipient.unread_notifications += 1
                db.session.commit()
            else:
                if recipient.instance.software == "lemmy" or recipient.instance.software == "mbin":
                    ap_type = "ChatMessage"
                else:
                    ap_type = "Note"
                # Federate reply
                reply_json = {
                    "actor": user.public_url(),
                    "id": f"https://{current_app.config['SERVER_NAME']}/activities/create/{gibberish(15)}",
                    "object": {
                        "attributedTo": user.public_url(),
                        "content": reply.body_html,
                        "id": reply.ap_id,
                        "inReplyTo": conversation.last_ap_id(recipient.id),
                        "mediaType": "text/html",
                        "published": utcnow().isoformat() + 'Z',  # Lemmy is inconsistent with the date format they use
                        "to": [
                            recipient.public_url()
                        ],
                        "type": ap_type
                    },
                    "to": [
                        recipient.public_url()
                    ],
                    "type": "Create"
                }
                if recipient.instance.software != "lemmy" and recipient.instance.software != "piefed":
                    reply_json['object']['tag'] = [
                        {
                            "href": recipient.public_url(),
                            "name": recipient.mention_tag(),
                            "type": "Mention"
                        }
                    ]
                send_post_request(recipient.ap_inbox_url, reply_json, user.private_key,
                                  user.public_url() + '#main-key')

    flash(_('Message sent.'))
    return reply
