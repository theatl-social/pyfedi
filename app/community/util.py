from __future__ import annotations

from datetime import datetime, timedelta
from time import sleep
from random import randint
from typing import List

import httpx
from PIL import Image, ImageOps
from flask import request, abort, g, current_app, json
from flask_login import current_user
from pillow_heif import register_heif_opener

from app import db, cache, celery
from app.activitypub.signature import post_request, default_context, send_post_request
from app.activitypub.util import find_actor_or_create, actor_json_to_model, ensure_domains_match, \
    find_hashtag_or_create, create_post, remote_object_to_json
from app.models import Community, File, BannedInstances, PostReply, Post, utcnow, CommunityMember, Site, \
    Instance, User, Tag
from app.utils import get_request, gibberish, ensure_directory_exists, ap_datetime, instance_banned, get_task_session
from sqlalchemy import func, desc
import os


allowed_extensions = ['.gif', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.mpo', '.avif', '.svg']


def search_for_community(address: str) -> Community | None:
    if address.startswith('!'):
        name, server = address[1:].split('@')

        banned = BannedInstances.query.filter_by(domain=server).first()
        if banned:
            return None

        if current_app.config['SERVER_NAME'] == server:
            already_exists = Community.query.filter_by(name=name, ap_id=None).first()
            return already_exists

        already_exists = Community.query.filter_by(ap_id=address[1:]).first()
        if already_exists:
            return already_exists

        # Look up the profile address of the community using WebFinger
        try:
            webfinger_data = get_request(f"https://{server}/.well-known/webfinger",
                                         params={'resource': f"acct:{address[1:]}"})
        except httpx.HTTPError:
            sleep(randint(3, 10))
            try:
                webfinger_data = get_request(f"https://{server}/.well-known/webfinger",
                                            params={'resource': f"acct:{address[1:]}"})
            except httpx.HTTPError:
                return None

        if webfinger_data.status_code == 200:
            webfinger_json = webfinger_data.json()
            for links in webfinger_json['links']:
                if 'rel' in links and links['rel'] == 'self':  # this contains the URL of the activitypub profile
                    type = links['type'] if 'type' in links else 'application/activity+json'
                    # retrieve the activitypub profile
                    community_data = get_request(links['href'], headers={'Accept': type})
                    # to see the structure of the json contained in community_data, do a GET to https://lemmy.world/c/technology with header Accept: application/activity+json
                    if community_data.status_code == 200:
                        try:
                            community_json = community_data.json()
                            community_data.close()
                        except:
                            community_data.close()
                            return None
                        if community_json['type'] == 'Group':
                            community = actor_json_to_model(community_json, name, server)
                            if community:
                                if current_app.debug:
                                    retrieve_mods_and_backfill(community.id, server, name, community_json)
                                else:
                                    retrieve_mods_and_backfill.delay(community.id, server, name, community_json)
                            return community
        return None


@celery.task
def retrieve_mods_and_backfill(community_id: int, server, name, community_json=None):
    with current_app.app_context():
        community = Community.query.get(community_id)
        if not community:
            return
        site = Site.query.get(1)

        is_peertube = is_guppe = is_wordpress = False
        if community.ap_profile_id == f"https://{server}/video-channels/{name}":
            is_peertube = True
        elif community.ap_profile_id.startswith('https://a.gup.pe/u'):
            is_guppe = True

        # get mods
        if community.ap_moderators_url:
            mods_data = remote_object_to_json(community.ap_moderators_url)
            if mods_data and mods_data['type'] == 'OrderedCollection' and 'orderedItems' in mods_data:
                for actor in mods_data['orderedItems']:
                    sleep(0.5)
                    mod = find_actor_or_create(actor)
                    if mod:
                        existing_membership = CommunityMember.query.filter_by(community_id=community.id, user_id=mod.id).first()
                        if existing_membership:
                            existing_membership.is_moderator = True
                        else:
                            new_membership = CommunityMember(community_id=community.id, user_id=mod.id, is_moderator=True)
                            db.session.add(new_membership)
        elif community_json and 'attributedTo' in community_json:
            mods = community_json['attributedTo']
            if isinstance(mods, list):
                for m in mods:
                    if 'type' in m and m['type'] == 'Person' and 'id' in m:
                        mod = find_actor_or_create(m['id'])
                        if mod:
                            existing_membership = CommunityMember.query.filter_by(community_id=community.id, user_id=mod.id).first()
                            if existing_membership:
                                existing_membership.is_moderator = True
                            else:
                                new_membership = CommunityMember(community_id=community.id, user_id=mod.id, is_moderator=True)
                                db.session.add(new_membership)
        if is_peertube:
            community.restricted_to_mods = True
        db.session.commit()

        # only backfill nsfw if nsfw communities are allowed
        if (community.nsfw and not site.enable_nsfw) or (community.nsfl and not site.enable_nsfl):
            return

        # download 50 old posts from unpaginated outboxes or 10 posts from page 1 if outbox is paginated (with Celery, or just 2 without)
        if community.ap_outbox_url:
            outbox_data = remote_object_to_json(community.ap_outbox_url)
            if not outbox_data or ('totalItems' in outbox_data and outbox_data['totalItems'] == 0):
                return
            if 'first' in outbox_data:
                outbox_data = remote_object_to_json(outbox_data['first'])
                if not outbox_data:
                    return
                max = 10
            else:
                max = 50
            if current_app.debug:
                max = 2
            if 'type' in outbox_data and (outbox_data['type'] == 'OrderedCollection' or outbox_data['type'] == 'OrderedCollectionPage') and 'orderedItems' in outbox_data:
                activities_processed = 0
                for announce in outbox_data['orderedItems']:
                    activity = None
                    if is_peertube or is_guppe:
                        activity = remote_object_to_json(announce['object'])
                    elif 'object' in announce and 'object' in announce['object']:
                        activity = announce['object']['object']
                    elif 'type' in announce and announce['type'] == 'Create':
                        activity = announce['object']
                        is_wordpress = True
                    if not activity:
                        return
                    if not ensure_domains_match(activity):
                        continue
                    if is_peertube:
                        user = mod
                    elif 'attributedTo' in activity and isinstance(activity['attributedTo'], str):
                        user = find_actor_or_create(activity['attributedTo'])
                        if not user:
                            continue
                    else:
                        continue
                    if user.is_local():
                        continue
                    if is_peertube or is_guppe:
                        request_json = {'id': f"https://{server}/activities/create/{gibberish(15)}", 'object': activity}
                    elif is_wordpress:
                        request_json = announce
                    else:
                        request_json = announce['object']
                    post = create_post(True, community, request_json, user, announce['id'])
                    if post:
                        if 'published' in activity:
                            post.posted_at = activity['published']
                            post.last_active = activity['published']
                            db.session.commit()
                    activities_processed += 1
                    if activities_processed >= max:
                        break
                if community.post_count > 0:
                    community.last_active = Post.query.filter(Post.community_id == community.id).order_by(desc(Post.posted_at)).first().posted_at
                    db.session.commit()
        if community.ap_featured_url:
            featured_data = remote_object_to_json(community.ap_featured_url)
            if featured_data and 'type' in featured_data and featured_data['type'] == 'OrderedCollection' and 'orderedItems' in featured_data:
                for item in featured_data['orderedItems']:
                    post = Post.get_by_ap_id(item['id'])
                    if post:
                        post.sticky = True
                        db.session.commit()


def actor_to_community(actor) -> Community:
    actor = actor.strip()
    if '@' in actor:
        community = Community.query.filter_by(banned=False, ap_id=actor).first()
    else:
        community = Community.query.filter(func.lower(Community.name) == func.lower(actor)).filter_by(banned=False, ap_id=None).first()
    return community


def end_poll_date(end_choice):
    delta_mapping = {
        '30m': timedelta(minutes=30),
        '1h': timedelta(hours=1),
        '6h': timedelta(hours=6),
        '12h': timedelta(hours=12),
        '1d': timedelta(days=1),
        '3d': timedelta(days=3),
        '7d': timedelta(days=7)
    }

    if end_choice in delta_mapping:
        return datetime.utcnow() + delta_mapping[end_choice]
    else:
        raise ValueError("Invalid choice")


def tags_from_string(tags: str) -> List[dict]:
    return_value = []
    tags = tags.strip()
    if tags == '':
        return []
    tag_list = tags.split(',')
    tag_list = [tag.strip() for tag in tag_list]
    for tag in tag_list:
        if tag[0] == '#':
            tag = tag[1:]
        tag_to_append = find_hashtag_or_create(tag)
        if tag_to_append:
            return_value.append({'type': 'Hashtag', 'name': tag_to_append.name})
    return return_value


def tags_from_string_old(tags: str) -> List[Tag]:
    return_value = []
    tags = tags.strip()
    if tags == '':
        return []
    if tags[-1:] == ',':
        tags = tags[:-1]
    tag_list = tags.split(',')
    tag_list = [tag.strip() for tag in tag_list]
    for tag in tag_list:
        if tag[0] == '#':
            tag = tag[1:]
        tag_to_append = find_hashtag_or_create(tag)
        if tag_to_append and tag_to_append not in return_value:
            return_value.append(tag_to_append)
    return return_value


def delete_post_from_community(post_id):
    if current_app.debug:
        delete_post_from_community_task(post_id)
    else:
        delete_post_from_community_task.delay(post_id)


@celery.task
def delete_post_from_community_task(post_id):
    post = Post.query.get(post_id)
    community = post.community
    post.deleted = True
    post.deleted_by = current_user.id
    db.session.commit()

    if not community.local_only:
        delete_json = {
            'id': f"https://{current_app.config['SERVER_NAME']}/activities/delete/{gibberish(15)}",
            'type': 'Delete',
            'actor': current_user.public_url(),
            'audience': post.community.public_url(),
            'to': [post.community.public_url(), 'https://www.w3.org/ns/activitystreams#Public'],
            'published': ap_datetime(utcnow()),
            'cc': [
                current_user.followers_url()
            ],
            'object': post.ap_id,
        }

        if not post.community.is_local():  # this is a remote community, send it to the instance that hosts it
            send_post_request(post.community.ap_inbox_url, delete_json, current_user.private_key, current_user.public_url() + '#main-key')
        else:  # local community - send it to followers on remote instances
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
                if instance.inbox and not current_user.has_blocked_instance(instance.id) and not instance_banned(
                        instance.domain):
                    send_to_remote_instance(instance.id, post.community.id, announce)


def delete_post_reply_from_community(post_reply_id):
    if current_app.debug:
        delete_post_reply_from_community_task(post_reply_id)
    else:
        delete_post_reply_from_community_task.delay(post_reply_id)


@celery.task
def delete_post_reply_from_community_task(post_reply_id):
    post_reply = PostReply.query.get(post_reply_id)
    post = post_reply.post
    community = post.community
    if post_reply.user_id == current_user.id or community.is_moderator():
        post_reply.deleted = True
        post_reply.deleted_by = current_user.id
        db.session.commit()

        # federate delete
        if not post.community.local_only:
            delete_json = {
                'id': f"https://{current_app.config['SERVER_NAME']}/activities/delete/{gibberish(15)}",
                'type': 'Delete',
                'actor': current_user.public_url(),
                'audience': post.community.public_url(),
                'to': [post.community.public_url(), 'https://www.w3.org/ns/activitystreams#Public'],
                'published': ap_datetime(utcnow()),
                'cc': [
                    current_user.followers_url()
                ],
                'object': post_reply.ap_id,
            }

            if not post.community.is_local():  # this is a remote community, send it to the instance that hosts it
                send_post_request(post.community.ap_inbox_url, delete_json, current_user.private_key, current_user.public_url() + '#main-key')

            else:  # local community - send it to followers on remote instances
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
                    if instance.inbox and not current_user.has_blocked_instance(instance.id) and not instance_banned(
                            instance.domain):
                        send_to_remote_instance(instance.id, post.community.id, announce)


def remove_old_file(file_id):
    remove_file = File.query.get(file_id)
    remove_file.delete_from_disk()


def save_icon_file(icon_file, directory='communities') -> File:
    # check if this is an allowed type of file
    file_ext = os.path.splitext(icon_file.filename)[1]
    if file_ext.lower() not in allowed_extensions:
        abort(400)
    new_filename = gibberish(15)

    # set up the storage directory
    directory = f'app/static/media/{directory}/' + new_filename[0:2] + '/' + new_filename[2:4]
    ensure_directory_exists(directory)

    # save the file
    final_place = os.path.join(directory, new_filename + file_ext)
    final_place_thumbnail = os.path.join(directory, new_filename + '_thumbnail.webp')
    icon_file.save(final_place)

    if file_ext.lower() == '.heic':
        register_heif_opener()
    elif file_ext.lower() == '.avif':
        import pillow_avif

    # resize if necessary
    if file_ext.lower() in allowed_extensions:
        if file_ext.lower() == '.svg':  # svgs don't need to be resized
            file = File(file_path=final_place, file_name=new_filename + file_ext, alt_text=f'{directory} icon',
                        thumbnail_path=final_place)
            db.session.add(file)
            return file
        else:
            Image.MAX_IMAGE_PIXELS = 89478485
            img = Image.open(final_place)
            img = ImageOps.exif_transpose(img)
            img_width = img.width
            img_height = img.height
            if img.width > 250 or img.height > 250:
                img.thumbnail((250, 250))
                img.save(final_place)
                img_width = img.width
                img_height = img.height
            # save a second, smaller, version as a thumbnail
            img.thumbnail((40, 40))
            img.save(final_place_thumbnail, format="WebP", quality=93)
            thumbnail_width = img.width
            thumbnail_height = img.height

            file = File(file_path=final_place, file_name=new_filename + file_ext, alt_text=f'{directory} icon',
                        width=img_width, height=img_height, thumbnail_width=thumbnail_width,
                        thumbnail_height=thumbnail_height, thumbnail_path=final_place_thumbnail)
            db.session.add(file)
            return file
    else:
        abort(400)


def save_banner_file(banner_file, directory='communities') -> File:
    # check if this is an allowed type of file
    file_ext = os.path.splitext(banner_file.filename)[1]
    if file_ext.lower() not in allowed_extensions:
        abort(400)
    new_filename = gibberish(15)

    # set up the storage directory
    directory = f'app/static/media/{directory}/' + new_filename[0:2] + '/' + new_filename[2:4]
    ensure_directory_exists(directory)

    # save the file
    final_place = os.path.join(directory, new_filename + file_ext)
    final_place_thumbnail = os.path.join(directory, new_filename + '_thumbnail.webp')
    banner_file.save(final_place)

    if file_ext.lower() == '.heic':
        register_heif_opener()
    elif file_ext.lower() == '.avif':
        import pillow_avif

    # resize if necessary
    Image.MAX_IMAGE_PIXELS = 89478485
    img = Image.open(final_place)
    if '.' + img.format.lower() in allowed_extensions:
        img = ImageOps.exif_transpose(img)
        img_width = img.width
        img_height = img.height
        if img.width > 1600 or img.height > 600:
            img.thumbnail((1600, 600))
            img.save(final_place)
            img_width = img.width
            img_height = img.height

        # save a second, smaller, version as a thumbnail
        img.thumbnail((878, 500))
        img.save(final_place_thumbnail, format="WebP", quality=93)
        thumbnail_width = img.width
        thumbnail_height = img.height

        file = File(file_path=final_place, file_name=new_filename + file_ext, alt_text=f'{directory} banner',
                    width=img_width, height=img_height, thumbnail_path=final_place_thumbnail,
                    thumbnail_width=thumbnail_width, thumbnail_height=thumbnail_height)
        db.session.add(file)
        return file
    else:
        abort(400)


# NB this always signs POSTs as the community so is only suitable for Announce activities
def send_to_remote_instance(instance_id: int, community_id: int, payload):
    if current_app.debug:
        send_to_remote_instance_task(instance_id, community_id, payload)
    else:
        send_to_remote_instance_task.delay(instance_id, community_id, payload)


@celery.task
def send_to_remote_instance_task(instance_id: int, community_id: int, payload):
    session = get_task_session()
    community: Community = session.query(Community).get(community_id)
    if community:
        instance: Instance = session.query(Instance).get(instance_id)
        if instance.inbox and instance.online() and not instance_banned(instance.domain):
            send_post_request(instance.inbox, payload, community.private_key, community.ap_profile_id + '#main-key', timeout=10)
    session.close()


def community_in_list(community_id, community_list):
    for tup in community_list:
        if community_id == tup[0]:
            return True
    return False


def find_local_users(search: str) -> List[User]:
    return User.query.filter(User.banned == False, User.deleted == False, User.ap_id == None, User.user_name.ilike(f"%{search}%")).\
        order_by(desc(User.reputation)).all()
