from time import sleep
from typing import List, Tuple

from flask import request, abort, g, current_app, json, flash, render_template
from flask_login import current_user
from sqlalchemy import text, desc
from flask_babel import _

from app import db, cache, celery
from app.activitypub.signature import default_context, send_post_request

from app.models import User, Community, Instance, Site, ActivityPubLog, CommunityMember, Language
from app.utils import gibberish, topic_tree, get_request


def unsubscribe_from_everything_then_delete(user_id):
    if current_app.debug:
        unsubscribe_from_everything_then_delete_task(user_id)
    else:
        unsubscribe_from_everything_then_delete_task.delay(user_id)


@celery.task
def unsubscribe_from_everything_then_delete_task(user_id):
    user = User.query.get(user_id)
    if user:
        # unsubscribe
        communities = CommunityMember.query.filter_by(user_id=user_id).all()
        for membership in communities:
            community = Community.query.get(membership.community_id)
            unsubscribe_from_community(community, user)

        # federate deletion of account
        if user.is_local():
            instances = Instance.query.filter(Instance.dormant == False).all()
            payload = {
                "@context": default_context(),
                "actor": user.public_url(),
                "id": f"{user.public_url()}#delete",
                "object": user.public_url(),
                "to": [
                    "https://www.w3.org/ns/activitystreams#Public"
                ],
                "type": "Delete"
            }
            for instance in instances:
                if instance.inbox and instance.online() and instance.id != 1:  # instance id 1 is always the current instance
                    send_post_request(instance.inbox, payload, user.private_key, f"{user.public_url()}#main-key")

        sleep(5)

        user.banned = True
        user.deleted = True
        user.delete_dependencies()
        db.session.commit()


def unsubscribe_from_community(community, user):
    if community.instance.gone_forever:
        return

    undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/" + gibberish(15)
    follow = {
        "actor": user.public_url(),
        "to": [community.public_url()],
        "object": community.public_url(),
        "type": "Follow",
        "id": f"https://{current_app.config['SERVER_NAME']}/activities/follow/{gibberish(15)}"
    }
    undo = {
        'actor': user.public_url(),
        'to': [community.public_url()],
        'type': 'Undo',
        'id': undo_id,
        'object': follow
    }
    send_post_request(community.ap_inbox_url, undo, user.private_key, user.public_url() + '#main-key')


def send_newsletter(form):
    recipients = User.query.filter(User.newsletter == True, User.banned == False, User.ap_id == None).order_by(desc(User.id)).limit(40000)

    from app.email import send_email

    if recipients.count() == 0:
        flash(_('No recipients'), 'error')

    for recipient in recipients:
        body_text = render_template('email/newsletter.txt',
                                    recipient=recipient if not form.test.data else current_user,
                                    content=form.body_text.data)
        body_html = render_template('email/newsletter.html',
                                    recipient=recipient if not form.test.data else current_user,
                                    content=form.body_html.data,
                                    domain=current_app.config['SERVER_NAME'])
        if form.test.data:
            to = current_user.email
        else:
            to = recipient.email

        send_email(subject=form.subject.data, sender=f'{g.site.name} <{current_app.config["MAIL_FROM"]}>', recipients=[to],
                   text_body=body_text, html_body=body_html)

        if form.test.data:
            break


def topics_for_form(current_topic: int) -> List[Tuple[int, str]]:
    result = [(0, _('None'))]
    topics = topic_tree()
    for topic in topics:
        if topic['topic'].id != current_topic:
            result.append((topic['topic'].id, topic['topic'].name))
        if topic['children']:
            result.extend(topics_for_form_children(topic['children'], current_topic, 1))
    return result


def topics_for_form_children(topics, current_topic: int, depth: int) -> List[Tuple[int, str]]:
    result = []
    for topic in topics:
        if topic['topic'].id != current_topic:
            result.append((topic['topic'].id, '--' * depth + ' ' + topic['topic'].name))
        if topic['children']:
            result.extend(topics_for_form_children(topic['children'], current_topic, depth + 1))
    return result

