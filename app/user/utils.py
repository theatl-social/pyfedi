from time import sleep

from flask import current_app, json

from app import celery, db
from app.activitypub.signature import post_request, default_context
from app.activitypub.util import actor_json_to_model
from app.community.util import send_to_remote_instance
from app.models import User, CommunityMember, Community, Instance, Site, utcnow, ActivityPubLog, BannedInstances
from app.utils import gibberish, ap_datetime, instance_banned, get_request


def purge_user_then_delete(user_id):
    if current_app.debug:
        purge_user_then_delete_task(user_id)
    else:
        purge_user_then_delete_task.delay(user_id)


@celery.task
def purge_user_then_delete_task(user_id):
    user = User.query.get(user_id)
    if user:
        # posts
        for post in user.posts:
            if not post.community.local_only:
                delete_json = {
                    'id': f"https://{current_app.config['SERVER_NAME']}/activities/delete/{gibberish(15)}",
                    'type': 'Delete',
                    'actor': user.public_url(),
                    'audience': post.community.public_url(),
                    'to': [post.community.public_url(), 'https://www.w3.org/ns/activitystreams#Public'],
                    'published': ap_datetime(utcnow()),
                    'cc': [
                        user.followers_url()
                    ],
                    'object': post.ap_id,
                }

                if not post.community.is_local():  # this is a remote community, send it to the instance that hosts it
                    success = post_request(post.community.ap_inbox_url, delete_json, user.private_key,
                                           user.public_url() + '#main-key')

                else:  # local community - send it to followers on remote instances, using Announce
                    announce = {
                        "id": f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}",
                        "type": 'Announce',
                        "to": [
                            "https://www.w3.org/ns/activitystreams#Public"
                        ],
                        "actor": post.community.ap_profile_id,
                        "cc": [
                            post.community.ap_followers_url
                        ],
                        '@context': default_context(),
                        'object': delete_json
                    }

                    for instance in post.community.following_instances():
                        if instance.inbox and not instance_banned(instance.domain):
                            send_to_remote_instance(instance.id, post.community.id, announce)

        # unsubscribe
        communities = CommunityMember.query.filter_by(user_id=user_id).all()
        for membership in communities:
            community = Community.query.get(membership.community_id)
            unsubscribe_from_community(community, user)

        # federate deletion of account
        if user.is_local():
            instances = Instance.query.all()
            payload = {
                "@context": default_context(),
                "actor": user.ap_profile_id,
                "id": f"{user.ap_profile_id}#delete",
                "object": user.ap_profile_id,
                "to": [
                    "https://www.w3.org/ns/activitystreams#Public"
                ],
                "type": "Delete"
            }
            for instance in instances:
                if instance.inbox and instance.id != 1:
                    post_request(instance.inbox, payload, user.private_key, user.public_url() + '#main-key')

        sleep(100)                                  # wait a while for any related activitypub traffic to die down.
        user.deleted = True
        user.delete_dependencies()
        user.purge_content()
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
    post_request(community.ap_inbox_url, undo, user.private_key, user.public_url() + '#main-key')


def search_for_user(address: str):
    if '@' in address:
        name, server = address.lower().split('@')
    else:
        name = address
        server = ''

    if server:
        banned = BannedInstances.query.filter_by(domain=server).first()
        if banned:
            reason = f" Reason: {banned.reason}" if banned.reason is not None else ''
            raise Exception(f"{server} is blocked.{reason}")
        already_exists = User.query.filter_by(ap_id=address).first()
    else:
        already_exists = User.query.filter_by(user_name=name).first()
    if already_exists:
        return already_exists

    # Look up the profile address of the user using WebFinger
    # todo: try, except block around every get_request
    webfinger_data = get_request(f"https://{server}/.well-known/webfinger",
                                 params={'resource': f"acct:{address[1:]}"})
    if webfinger_data.status_code == 200:
        webfinger_json = webfinger_data.json()
        for links in webfinger_json['links']:
            if 'rel' in links and links['rel'] == 'self':  # this contains the URL of the activitypub profile
                type = links['type'] if 'type' in links else 'application/activity+json'
                # retrieve the activitypub profile
                user_data = get_request(links['href'], headers={'Accept': type})
                # to see the structure of the json contained in community_data, do a GET to https://lemmy.world/c/technology with header Accept: application/activity+json
                if user_data.status_code == 200:
                    user_json = user_data.json()
                    user_data.close()
                    if user_json['type'] == 'Person' or user_json['type'] == 'Service':
                        user = actor_json_to_model(user_json, name, server)
                        return user
    return None
