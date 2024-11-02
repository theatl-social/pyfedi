from app import cache, celery, db
from app.activitypub.signature import default_context, post_request
from app.models import Community, CommunityBan, CommunityJoinRequest, CommunityMember, Notification, Post, PostReply, User, utcnow
from app.user.utils import search_for_user
from app.utils import community_membership, gibberish, joined_communities, instance_banned, ap_datetime, \
                      recently_upvoted_posts, recently_downvoted_posts, recently_upvoted_post_replies, recently_downvoted_post_replies

from flask import current_app
from flask_babel import _

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
  'tag': []         (not in Announce)
}
"""



@celery.task
def make_reply(send_async, user_id, reply_id, parent_id):
    send_reply(user_id, reply_id, parent_id)


@celery.task
def edit_reply(send_async, user_id, reply_id, parent_id):
    send_reply(user_id, reply_id, parent_id, edit=True)


def send_reply(user_id, reply_id, parent_id, edit=False):
    user = User.query.filter_by(id=user_id).one()
    reply = PostReply.query.filter_by(id=reply_id).one()
    if parent_id:
        parent = PostReply.query.filter_by(id=parent_id).one()
    else:
        parent = reply.post
    community = reply.community

    recipients = [parent.author]
    pattern = r"@([a-zA-Z0-9_.-]*)@([a-zA-Z0-9_.-]*)\b"
    matches = re.finditer(pattern, reply.body)
    for match in matches:
        recipient = None
        if match.group(2) == current_app.config['SERVER_NAME']:
            user_name = match.group(1)
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
                if ((not recipient.ap_id and recipient.user_name == existing_recipient.user_name) or
                    (recipient.ap_id and recipient.ap_id == existing_recipient.ap_id)):
                    add_recipient = False
                    break
            if add_recipient:
                recipients.append(recipient)

    if community.local_only:
        for recipient in recipients:
            if recipient.is_local() and recipient.id != parent.author.id:
                already_notified = cache.get(f'{recipient.id} notified of {reply.id}')
                if not already_notified:
                    cache.set(f'{recipient.id} notified of {reply.id}', True, timeout=86400)
                    notification = Notification(user_id=recipient.id, title=_('You have been mentioned in a comment'),
                                        url=f"https://{current_app.config['SERVER_NAME']}/comment/{reply.id}",
                                        author_id=user.id)
                    recipient.unread_notifications += 1
                    db.session.add(notification)
                    db.session.commit()

    if community.local_only or not community.instance.online():
        return

    banned = CommunityBan.query.filter_by(user_id=user_id, community_id=community.id).first()
    if banned:
        return
    if not community.is_local():
        if user.has_blocked_instance(community.instance.id) or instance_banned(community.instance.domain):
            return

    to = ["https://www.w3.org/ns/activitystreams#Public"]
    cc = [community.public_url()]
    tag = []
    for recipient in recipients:
        tag.append({'href': recipient.public_url(), 'name': recipient.mention_tag(), 'type': 'Mention'})
        cc.append(recipient.public_url())
    language = {'identifier': reply.language_code(), 'name': reply.language_name()}
    content_map = {reply.language_code(): reply.body_html}
    source = {'content': reply.body, 'mediaType': 'text/markdown'}
    note = {
      'id': reply.public_url(),
      'url': reply.public_url(),
      'type': 'Note',
      'attributedTo': user.public_url(),
      'to': to,
      'cc': cc,
      'tag': tag,
      'audience': community.public_url(),
      'content': reply.body_html,
      'mediaType': 'text/html',
      'source': source,
      'inReplyTo': parent.public_url(),
      'published': ap_datetime(reply.posted_at),
      'language': language,
      'contentMap': content_map,
      'distinguished': False,
    }
    if edit:
        note['updated']: ap_datetime(utcnow())

    activity = 'create' if not edit else 'update'
    create_id = f"https://{current_app.config['SERVER_NAME']}/activities/{activity}/{gibberish(15)}"
    type = 'Create' if not edit else 'Update'
    create = {
      'id': create_id,
      'type': type,
      'actor': user.public_url(),
      'object': note,
      'to': to,
      'cc': cc,
      '@context': default_context(),
      'tag': tag
    }

    domains_sent_to = [current_app.config['SERVER_NAME']]

    if community.is_local():
        del create['@context']

        announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
        actor = community.public_url()
        cc = [community.ap_followers_url]
        announce = {
          'id': announce_id,
          'type': 'Announce',
          'actor': community.public_url(),
          'object': create,
          'to': to,
          'cc': cc,
          '@context': default_context()
        }
        for instance in community.following_instances():
            if instance.inbox and instance.online() and not user.has_blocked_instance(instance.id) and not instance_banned(instance.domain):
                post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
                domains_sent_to.append(instance.domain)
    else:
        post_request(community.ap_inbox_url, create, user.private_key, user.public_url() + '#main-key')
        domains_sent_to.append(community.instance.domain)

    # send copy to anyone else Mentioned in reply. (mostly for other local users and users on microblog sites)
    for recipient in recipients:
        if recipient.instance.domain not in domains_sent_to:
            post_request(recipient.instance.inbox, create, user.private_key, user.public_url() + '#main-key')
        if recipient.is_local() and recipient.id != parent.author.id:
            already_notified = cache.get(f'{recipient.id} notified of {reply.id}')
            if not already_notified:
                cache.set(f'{recipient.id} notified of {reply.id}', True, timeout=86400)
                notification = Notification(user_id=recipient.id, title=_('You have been mentioned in a comment'),
                                        url=f"https://{current_app.config['SERVER_NAME']}/comment/{reply.id}",
                                        author_id=user.id)
                recipient.unread_notifications += 1
                db.session.add(notification)
                db.session.commit()



