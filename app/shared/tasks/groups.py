from app import celery
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import Community, User, utcnow
from app.utils import gibberish, ap_datetime, get_task_session, patch_db_session
from app.shared.community import get_comm_flair_list, comm_flair_ap_format

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
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                user = session.query(User).filter_by(id=user_id).one()
                community = session.query(Community).filter_by(id=community_id).one()
                if community.local_only:
                    return

                if not community.is_moderator(user):
                    return

                announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
                update_id = f"https://{current_app.config['SERVER_NAME']}/activities/update/{gibberish(15)}"
                group_id = (
                    f"https://{current_app.config['SERVER_NAME']}/c/{community.name}"
                )
                group = {
                    "id": group_id,
                    "type": "Group",
                    "attributedTo": group_id + "/moderators",
                    "name": community.title,
                    "preferredUsername": community.name,
                    "sensitive": True if community.nsfw or community.nsfl else False,
                    "published": ap_datetime(community.created_at),
                    "updated": ap_datetime(utcnow()),
                    "postingRestrictedToMods": community.restricted_to_mods,
                    "featured": group_id + "/featured",
                    "followers": group_id + "/followers",
                    "endpoints": {
                        "sharedInbox": f"https://{current_app.config['SERVER_NAME']}/inbox"
                    },
                    "inbox": group_id + "/inbox",
                    "outbox": group_id + "/outbox",
                    "publicKey": {
                        "id": group_id + "#main-key",
                        "owner": group_id,
                        "publicKeyPem": community.public_key,
                    },
                }
                if community.description_html:
                    group["summary"] = community.description_html
                if community.description:
                    group["source"] = {
                        "content": community.description,
                        "mediaType": "text/markdown",
                    }
                if community.icon_id:
                    if community.icon_image().startswith("http"):
                        group["icon"] = {"type": "Image", "url": community.icon_image()}
                    else:
                        group["icon"] = {
                            "type": "Image",
                            "url": f"https://{current_app.config['SERVER_NAME']}{community.icon_image()}",
                        }
                if community.image_id:
                    if community.header_image().startswith("http"):
                        group["image"] = {
                            "type": "Image",
                            "url": community.header_image(),
                        }
                    else:
                        group["image"] = {
                            "type": "Image",
                            "url": f"https://{current_app.config['SERVER_NAME']}{community.header_image()}",
                        }
                language = []
                for community_language in community.languages:
                    language.append(
                        {
                            "identifier": community_language.code,
                            "name": community_language.name,
                        }
                    )
                group["language"] = language

                group["tag"] = community.flair_for_ap(version=2)

                to = ["https://www.w3.org/ns/activitystreams#Public"]
                cc = [community.public_url()]
                update = {
                    "id": update_id,
                    "type": "Update",
                    "actor": user.public_url(),
                    "object": group,
                    "to": to,
                    "cc": cc,
                    "audience": community.public_url(),
                }
                if community.is_local():
                    announce = {
                        "id": announce_id,
                        "type": "Announce",
                        "actor": community.public_url(),
                        "object": update,
                        "to": to,
                        "cc": cc,
                        "@context": default_context(),
                    }

                    for instance in community.following_instances():
                        if instance.inbox and instance.online():
                            send_post_request(
                                instance.inbox,
                                announce,
                                community.private_key,
                                community.public_url() + "#main-key",
                            )
                else:
                    send_post_request(
                        community.ap_inbox_url,
                        update,
                        user.private_key,
                        user.public_url() + "#main-key",
                    )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
