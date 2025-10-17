import random
import time
from time import sleep

from flask import current_app, json

from app import celery, db
from app.activitypub.signature import (
    post_request,
    default_context,
    signed_get_request,
    send_post_request,
)
from app.activitypub.util import actor_json_to_model
from app.community.util import send_to_remote_instance, send_to_remote_instance_fast
from app.models import (
    User,
    CommunityMember,
    Community,
    Instance,
    Site,
    utcnow,
    ActivityPubLog,
    BannedInstances,
)
from app.utils import gibberish, ap_datetime, instance_banned, get_request

import httpx


def purge_user_then_delete(user_id, flush=True):
    if current_app.debug:
        purge_user_then_delete_task(user_id, flush)
    else:
        purge_user_then_delete_task.delay(user_id, flush)


@celery.task
def purge_user_then_delete_task(user_id, flush):
    with current_app.app_context():
        user = User.query.get(user_id)
        if user:
            # posts
            for post in user.posts:
                if not post.community.local_only:
                    delete_json = {
                        "id": f"https://{current_app.config['SERVER_NAME']}/activities/delete/{gibberish(15)}",
                        "type": "Delete",
                        "actor": user.public_url(),
                        "audience": post.community.public_url(),
                        "to": [
                            post.community.public_url(),
                            "https://www.w3.org/ns/activitystreams#Public",
                        ],
                        "published": ap_datetime(utcnow()),
                        "cc": [user.followers_url()],
                        "object": post.ap_id,
                    }

                    if not post.community.is_local():  # this is a remote community, send it to the instance that hosts it
                        send_post_request(
                            post.community.ap_inbox_url,
                            delete_json,
                            user.private_key,
                            user.public_url() + "#main-key",
                        )

                    else:  # local community - send it to followers on remote instances, using Announce
                        announce = {
                            "id": f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}",
                            "type": "Announce",
                            "to": ["https://www.w3.org/ns/activitystreams#Public"],
                            "actor": post.community.ap_profile_id,
                            "cc": [post.community.ap_followers_url],
                            "@context": default_context(),
                            "object": delete_json,
                        }

                        for instance in post.community.following_instances():
                            if instance.inbox and not instance_banned(instance.domain):
                                send_to_remote_instance_fast(
                                    instance.inbox,
                                    post.community.private_key,
                                    post.community.ap_profile_id,
                                    announce,
                                )

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
                    "actor": user.public_url(),
                    "id": f"https://{current_app.config['SERVER_NAME']}/activities/delete/{gibberish(15)}",
                    "object": user.public_url(),
                    "to": ["https://www.w3.org/ns/activitystreams#Public"],
                    "type": "Delete",
                }
                for instance in instances:
                    if instance.inbox and instance.online() and instance.id != 1:
                        send_post_request(
                            instance.inbox,
                            payload,
                            user.private_key,
                            user.public_url() + "#main-key",
                        )

            user.delete_dependencies()
            user.purge_content(flush)
            from app import redis_client

            with redis_client.lock(
                f"lock:user:{user.id}", timeout=10, blocking_timeout=6
            ):
                user = User.query.get(user_id)
                user.deleted = True
                db.session.commit()


def unsubscribe_from_community(community, user):
    if community.instance.gone_forever or community.instance.dormant:
        return

    undo_id = (
        f"https://{current_app.config['SERVER_NAME']}/activities/undo/" + gibberish(15)
    )
    follow = {
        "actor": user.public_url(),
        "to": [community.public_url()],
        "object": community.public_url(),
        "type": "Follow",
        "id": f"https://{current_app.config['SERVER_NAME']}/activities/follow/{gibberish(15)}",
    }
    undo = {
        "actor": user.public_url(),
        "to": [community.public_url()],
        "type": "Undo",
        "id": undo_id,
        "object": follow,
    }
    send_post_request(
        community.ap_inbox_url, undo, user.private_key, user.public_url() + "#main-key"
    )


def search_for_user(address: str):
    if address.startswith("@"):
        address = address[1:]
    if "@" in address:
        name, server = address.lower().split("@")
    else:
        name = address
        server = ""

    if server:
        banned = BannedInstances.query.filter_by(domain=server).first()
        if banned:
            reason = f" Reason: {banned.reason}" if banned.reason is not None else ""
            raise Exception(f"{server} is blocked.{reason}")
        already_exists = User.query.filter_by(ap_id=address).first()
    else:
        already_exists = User.query.filter_by(user_name=name, ap_id=None).first()
    if already_exists:
        return already_exists

    if not server:
        return None

    # Look up the profile address of the user using WebFinger
    # todo: try, except block around every get_request
    webfinger_data = get_request(
        f"https://{server}/.well-known/webfinger",
        params={"resource": f"acct:{address}"},
    )
    if webfinger_data.status_code == 200:
        try:
            webfinger_json = webfinger_data.json()
            webfinger_data.close()
        except:
            webfinger_data.close()
            return None
        for links in webfinger_json["links"]:
            if (
                "rel" in links and links["rel"] == "self"
            ):  # this contains the URL of the activitypub profile
                type = links["type"] if "type" in links else "application/activity+json"
                # retrieve the activitypub profile
                for attempt in [1, 2]:
                    try:
                        object_request = get_request(
                            links["href"], headers={"Accept": type}
                        )
                    except httpx.HTTPError:
                        if attempt == 1:
                            time.sleep(3 + random.randrange(3))
                        else:
                            return None
                if object_request.status_code == 401:
                    site = Site.query.get(1)
                    for attempt in [1, 2]:
                        try:
                            object_request = signed_get_request(
                                links["href"],
                                site.private_key,
                                f"https://{current_app.config['SERVER_NAME']}/actor#main-key",
                            )
                        except httpx.HTTPError:
                            if attempt == 1:
                                time.sleep(3)
                            else:
                                return None
                if object_request.status_code == 200:
                    try:
                        object = object_request.json()
                        object_request.close()
                    except:
                        object_request.close()
                        return None
                else:
                    return None

                if object["type"] == "Person" or object["type"] == "Service":
                    user = actor_json_to_model(object, name, server)
                    return user

    return None
