import json
from app import cache, celery, db
from app.activitypub.signature import default_context, post_request, send_post_request
from app.constants import NOTIF_MENTION
from app.models import (
    Community,
    CommunityBan,
    CommunityJoinRequest,
    CommunityMember,
    Notification,
    Post,
    PostReply,
    utcnow,
    User,
)
from app.user.utils import search_for_user
from app.utils import (
    community_membership,
    gibberish,
    joined_communities,
    instance_banned,
    ap_datetime,
    recently_upvoted_posts,
    recently_downvoted_posts,
    recently_upvoted_post_replies,
    recently_downvoted_post_replies,
    get_recipient_language,
    get_task_session,
)

from flask import current_app
from flask_babel import _, force_locale, gettext

import re


""" Reply JSON format
{
  'id':
  'url':
  'type':
  'attributedTo':
  'to': []
  'cc': []
  'tag': []
  'audience':
  'content':
  'mediaType':
  'source': {}
  'inReplyTo':
  'published':
  'updated':        (inner oject of Update only)
  'language': {}
  'contentMap':{}
  'distinguished'
}
"""
""" Create / Update / Announce JSON format
{
  'id':
  'type':
  'actor':
  'object':
  'to': []
  'cc': []
  '@context':       (outer object only)
  'audience':       (not in Announce)
}
"""


@celery.task
def make_reply(send_async, reply_id, parent_id):
    session = get_task_session()
    try:
        send_reply(reply_id, parent_id, session=session)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@celery.task
def edit_reply(send_async, reply_id, parent_id):
    session = get_task_session()
    try:
        send_reply(reply_id, parent_id, edit=True, session=session)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def send_reply(reply_id, parent_id, edit=False, session=None):
    reply = session.query(PostReply).filter_by(id=reply_id).one()
    user = reply.author
    if parent_id:
        parent = session.query(PostReply).filter_by(id=parent_id).one()
    else:
        parent = reply.post
    community = reply.community

    # Find any users Mentioned in reply with @user@instance syntax
    recipients = [parent.author]
    pattern = r"@([a-zA-Z0-9_.-]*)@([a-zA-Z0-9_.-]*)\b"
    matches = re.finditer(pattern, reply.body)
    for match in matches:
        recipient = None
        if match.group(2) == current_app.config["SERVER_NAME"]:
            user_name = match.group(1)
            if user_name != user.user_name:
                try:
                    recipient = search_for_user(user_name)
                except:
                    pass
        else:
            ap_id = f"{match.group(1)}@{match.group(2)}"
            try:
                recipient = search_for_user(ap_id)
            except:
                pass
        if recipient:
            add_recipient = True
            for existing_recipient in recipients:
                if (
                    not recipient.ap_id
                    and recipient.user_name == existing_recipient.user_name
                ) or (recipient.ap_id and recipient.ap_id == existing_recipient.ap_id):
                    add_recipient = False
                    break
            if add_recipient:
                recipients.append(recipient)

    # Notify any local users that have been Mentioned
    for recipient in recipients:
        if recipient.is_local() and recipient.id != parent.author.id:
            if edit:
                existing_notification = (
                    session.query(Notification)
                    .filter(
                        Notification.user_id == recipient.id,
                        Notification.url
                        == f"https://{current_app.config['SERVER_NAME']}/comment/{reply.id}",
                    )
                    .first()
                )
            else:
                existing_notification = None
            if not existing_notification:
                author = session.query(User).get(user.id)
                targets_data = {
                    "gen": "0",
                    "post_id": reply.post_id,
                    "author_user_name": author.ap_id
                    if author.ap_id
                    else author.user_name,
                    "comment_id": reply.id,
                    "comment_body": reply.body,
                }
                with force_locale(get_recipient_language(recipient.id)):
                    notification = Notification(
                        user_id=recipient.id,
                        title=gettext(f"You have been mentioned in comment {reply.id}"),
                        url=f"https://{current_app.config['SERVER_NAME']}/comment/{reply.id}",
                        author_id=user.id,
                        notif_type=NOTIF_MENTION,
                        subtype="comment_mention",
                        targets=targets_data,
                    )
                    recipient.unread_notifications += 1
                    session.add(notification)
                    session.commit()

    if community.local_only or not community.instance.online():
        return

    banned = (
        session.query(CommunityBan)
        .filter_by(user_id=user.id, community_id=community.id)
        .first()
    )
    if banned:
        return
    if not community.is_local():
        if user.has_blocked_instance(community.instance.id) or instance_banned(
            community.instance.domain
        ):
            return

    to = ["https://www.w3.org/ns/activitystreams#Public"]
    cc = [community.public_url()]
    tag = []
    for recipient in recipients:
        tag.append(
            {
                "href": recipient.public_url(),
                "name": recipient.mention_tag(),
                "type": "Mention",
            }
        )
        cc.append(recipient.public_url())
    tag.extend(reply.tags_for_activitypub())
    language = {"identifier": reply.language_code(), "name": reply.language_name()}
    content_map = {reply.language_code(): reply.body_html}
    source = {"content": reply.body, "mediaType": "text/markdown"}
    note = {
        "id": reply.public_url(),
        "url": reply.public_url(),
        "type": "Note",
        "attributedTo": user.public_url(),
        "to": to,
        "cc": cc,
        "tag": tag,
        "audience": community.public_url(),
        "content": reply.body_html,
        "mediaType": "text/html",
        "source": source,
        "inReplyTo": parent.public_url(),
        "published": ap_datetime(reply.posted_at),
        "language": language,
        "contentMap": content_map,
        "distinguished": reply.distinguished,
        "flair": user.community_flair(reply.community_id),
    }
    if edit:
        note["updated"] = ap_datetime(utcnow())

    activity = "create" if not edit else "update"
    create_id = f"https://{current_app.config['SERVER_NAME']}/activities/{activity}/{gibberish(15)}"
    type = "Create" if not edit else "Update"
    create = {
        "id": create_id,
        "type": type,
        "actor": user.public_url(),
        "object": note,
        "to": to,
        "cc": cc,
        "@context": default_context(),
        "audience": community.public_url(),
    }

    domains_sent_to = [current_app.config["SERVER_NAME"]]

    # send the activity as an Announce if the community is local, or as a Create if not
    if community.is_local():
        del create["@context"]

        announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
        cc = [community.ap_followers_url]
        announce = {
            "id": announce_id,
            "type": "Announce",
            "actor": community.public_url(),
            "object": create,
            "to": to,
            "cc": cc,
            "@context": default_context(),
        }
        for instance in community.following_instances():
            if (
                instance.inbox
                and instance.online()
                and not user.has_blocked_instance(instance.id)
                and not instance_banned(instance.domain)
            ):
                send_post_request(
                    instance.inbox,
                    announce,
                    community.private_key,
                    community.public_url() + "#main-key",
                )
                domains_sent_to.append(instance.domain)
    else:
        send_post_request(
            community.ap_inbox_url,
            create,
            user.private_key,
            user.public_url() + "#main-key",
        )
        domains_sent_to.append(community.instance.domain)

    # send copy of the Create to anyone else Mentioned in reply, but not on an instance that's already sent to.
    if "@context" not in create:
        create["@context"] = default_context()
    for recipient in recipients:
        if recipient.instance.domain not in domains_sent_to:
            send_post_request(
                recipient.instance.inbox,
                create,
                user.private_key,
                user.public_url() + "#main-key",
            )


@celery.task
def choose_answer(send_async, post_reply_id, user_id):
    send_answer(post_reply_id, user_id, False)


@celery.task
def unchoose_answer(send_async, post_reply_id, user_id):
    send_answer(post_reply_id, user_id, True)


def send_answer(post_reply_id, user_id, is_undo):
    session = get_task_session()
    try:
        user = session.query(User).get(user_id)
        post_reply = session.query(PostReply).get(post_reply_id)

        if (
            post_reply.community.local_only
            or not post_reply.community.instance.online()
        ):
            return

        answer_ap_id = f"https://{current_app.config['SERVER_NAME']}/activities/answer/{gibberish(15)}"
        to = ["https://www.w3.org/ns/activitystreams#Public"]
        cc = [post_reply.community.public_url()]
        lock = {
            "id": answer_ap_id,
            "type": "ChooseAnswer",
            "actor": user.public_url(),
            "object": post_reply.public_url(),
            "@context": default_context(),
            "audience": post_reply.community.public_url(),
            "to": to,
            "cc": cc,
        }

        if is_undo:
            del lock["@context"]
            undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"
            undo = {
                "id": undo_id,
                "type": "Undo",
                "actor": user.public_url(),
                "object": lock,
                "@context": default_context(),
                "audience": post_reply.community.public_url(),
                "to": to,
                "cc": cc,
            }

        if post_reply.community.is_local():
            if is_undo:
                del undo["@context"]
                object = undo
            else:
                del lock["@context"]
                object = lock

            announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
            actor = post_reply.community.public_url()
            cc = [post_reply.community.ap_followers_url]
            announce = {
                "id": announce_id,
                "type": "Announce",
                "actor": actor,
                "object": object,
                "@context": default_context(),
                "to": to,
                "cc": cc,
            }
            for instance in post_reply.community.following_instances():
                if (
                    instance.inbox
                    and instance.online()
                    and not user.has_blocked_instance(instance.id)
                    and not instance_banned(instance.domain)
                ):
                    send_post_request(
                        instance.inbox,
                        announce,
                        post_reply.community.private_key,
                        post_reply.community.public_url() + "#main-key",
                    )
        else:
            payload = undo if is_undo else lock
            send_post_request(
                post_reply.community.ap_inbox_url,
                payload,
                user.private_key,
                user.public_url() + "#main-key",
            )

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
