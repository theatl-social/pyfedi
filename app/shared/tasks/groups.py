from app import celery
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import Community, User, utcnow
from app.utils import gibberish, ap_datetime

from flask import current_app


"""
Group JSON format:
{
  'id':
  'type':
  'attributedTo':
  'name':
  'preferredUsername':
  'sensitive':
  'published':
  'updated':
  'summary':
  'source': {}
  'icon':
  'image':
  'language': []
  'postingRestrictedToMods':
  'featured':
  'followers':
  'endpoints': {}
  'inbox':
  'outbox':
  'publicKey': {}
}
"""
""" Update / Announce JSON format
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


# this is only for local communities (local users can moderate remote communities, but the Update won't accepted if they edit them)

@celery.task
def edit_community(send_async, user_id, community_id):
    user = User.query.filter_by(id=user_id).one()
    community = Community.query.filter_by(id=community_id).one()
    if community.local_only:
        return

    if not community.is_local():
        return

    announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
    update_id = f"https://{current_app.config['SERVER_NAME']}/activities/update/{gibberish(15)}"
    group_id = f"https://{current_app.config['SERVER_NAME']}/c/{community.name}"
    group = {
      'id': group_id,
      'type': 'Group',
      'attributedTo': group_id + '/moderators',
      'name': community.title,
      'preferredUsername': community.name,
      'sensitive': True if community.nsfw or community.nsfl else False,
      'published': ap_datetime(community.created_at),
      'updated': ap_datetime(utcnow()),
      'postingRestrictedToMods': community.restricted_to_mods,
      'featured': group_id + '/featured',
      'followers': group_id + '/followers',
      'endpoints': {'sharedInbox': f"https://{current_app.config['SERVER_NAME']}/inbox"},
      'inbox': group_id + '/inbox',
      'outbox': group_id + '/outbox',
      'publicKey':  {'id': group_id + '#main-key', 'owner': group_id, 'publicKeyPem': community.public_key}
    }
    if community.description_html:
        group['summary'] = community.description_html
    if community.description:
        group['source'] = {'content': community.description, 'mediaType': 'text/markdown'}
    if community.icon_id:
        group['icon'] = {
          'type': 'Image',
          'url': f"https://{current_app.config['SERVER_NAME']}{community.icon_image()}"
        }
    if community.image_id:
        group['image'] = {
          'type': 'Image',
          'url': f"https://{current_app.config['SERVER_NAME']}{community.header_image()}"
    }
    language = []
    for community_language in community.languages:
        language.append({'identifier': community_language.code, 'name': community_language.name})
    group['language'] = language

    to = ['https://www.w3.org/ns/activitystreams#Public']
    cc = [community.public_url()]
    update = {
      'id': update_id,
      'type': 'Update',
      'actor': user.public_url(),
      'object': group,
      'to': to,
      'cc': cc,
      'audience': community.public_url()
    }
    announce = {
      'id': announce_id,
      'type': 'Announce',
      'actor': community.public_url(),
      'object': update,
      'to': to,
      'cc': cc,
      '@context': default_context()
    }

    for instance in community.following_instances():
        if instance.inbox and instance.online():
            send_post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
