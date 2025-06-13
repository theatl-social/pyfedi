import datetime

from app import celery
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import Community, User
from app.utils import gibberish, ap_datetime

from flask import current_app


""" JSON format
Block:
{
  'id':
  'type':
  'actor':        # person doing the ban
  'object':       # person being banned
  'target':       # community (or site)
  '@context':
  'audience':
  'to': []
  'cc': []
  'endTime':
  'expires':
  'removeData':
  'summary':
}
Announce:
remove @context from inner object
{
  '@context':
  'actor':        # community
  'cc':
  'to':
  'type':
  'object':
}
"""


""" TODO
@celery.task
def ban_from_site():
    ban_person()
"""


@celery.task
def ban_from_community(send_async, user_id, mod_id, community_id, expiry, reason):
    ban_person(user_id, mod_id, community_id,  expiry, reason)


@celery.task
def unban_from_community(send_async, user_id, mod_id, community_id, expiry, reason):
    ban_person(user_id, mod_id, community_id,  expiry, reason, is_undo=True)


def ban_person(user_id, mod_id, community_id, expiry, reason, is_undo=False):
    if expiry is None:
        expiry = datetime.datetime(year=2100, month=1, day=1)
    user = User.query.filter_by(id=user_id).one()
    mod = User.query.filter_by(id=mod_id).one()
    community = Community.query.filter_by(id=community_id).one()
    if community.local_only:
        return

    block_id = f"https://{current_app.config['SERVER_NAME']}/activities/block/{gibberish(15)}"
    to = ["https://www.w3.org/ns/activitystreams#Public"]
    cc = [community.public_url()]
    block = {
      'id': block_id,
      'type': 'Block',
      'actor': mod.public_url(),
      'object': user.public_url(),
      'target': community.public_url(),
      '@context': default_context(),
      'audience': community.public_url(),
      'to': to,
      'cc': cc,
      'endTime': ap_datetime(expiry),
      'expires': ap_datetime(expiry),
      'removeData': False,
      'summary': reason
    }

    if is_undo:
        del block['@context']
        undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"
        undo = {
          'id': undo_id,
          'type': 'Undo',
          'actor': mod.public_url(),
          'object': block,
          '@context': default_context(),
          'audience': community.public_url(),
          'to': to,
          'cc': cc
        }

    if is_undo:
        del undo['@context']
        object=undo
    else:
        del block['@context']
        object=block

    if community.is_local():
        announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
        cc = [community.ap_followers_url]
        announce = {
          'id': announce_id,
          'type': 'Announce',
          'actor': community.public_url(),
          'object': object,
          '@context': default_context(),
          'to': to,
          'cc': cc
        }
        sent_to = set()
        for instance in community.following_instances():
            sent_to.add(instance.id)
            if instance.inbox and instance.online():
                send_post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
        if user.instance_id not in sent_to:     # community.following_instances() excludes instances where banned people are the only follower and they've just been banned so they may be no other followers from that instance.
            send_post_request(user.instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
    else:
        send_post_request(community.ap_inbox_url, object, mod.private_key, mod.public_url() + '#main-key')
