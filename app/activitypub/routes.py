from datetime import timedelta
from random import randint

from flask import request, current_app, abort, jsonify, json, g, url_for, redirect, make_response
from flask_login import current_user
from sqlalchemy import desc, or_
import werkzeug.exceptions

from app import db, constants, cache, celery
from app.activitypub import bp

from app.activitypub.signature import HttpSignature, post_request, VerificationError, default_context, LDSignature
from app.community.routes import show_community
from app.community.util import send_to_remote_instance
from app.post.routes import continue_discussion, show_post
from app.user.routes import show_profile
from app.constants import *
from app.models import User, Community, CommunityJoinRequest, CommunityMember, CommunityBan, ActivityPubLog, Post, \
    PostReply, Instance, PostVote, PostReplyVote, File, AllowedInstances, BannedInstances, utcnow, Site, Notification, \
    ChatMessage, Conversation, UserFollower, UserBlock, Poll, PollChoice
from app.activitypub.util import public_key, users_total, active_half_year, active_month, local_posts, local_comments, \
    post_to_activity, find_actor_or_create, instance_blocked, find_reply_parent, find_liked_object, \
    lemmy_site_data, is_activitypub_request, delete_post_or_comment, community_members, \
    user_removed_from_remote_server, create_post, create_post_reply, update_post_reply_from_activity, \
    update_post_from_activity, undo_vote, undo_downvote, post_to_page, get_redis_connection, find_reported_object, \
    process_report, ensure_domains_match, can_edit, can_delete, remove_data_from_banned_user, resolve_remote_post, \
    inform_followers_of_post_update, comment_model_to_json, restore_post_or_comment, ban_user, unban_user, \
    log_incoming_ap, find_community_ap_id, site_ban_remove_data, community_ban_remove_data
from app.utils import gibberish, get_setting, render_template, \
    community_membership, ap_datetime, ip_address, can_downvote, \
    can_upvote, can_create_post, awaken_dormant_instance, shorten_string, can_create_post_reply, sha256_digest, \
    community_moderators, markdown_to_html, html_to_text, add_to_modlog_activitypub


@bp.route('/testredis')
def testredis_get():
    redis_client = get_redis_connection()
    redis_client.set("cowbell", "1", ex=600)
    x = redis_client.get('cowbell')
    if x is not None:
        return "Redis: OK"
    else:
        return "Redis: FAIL"


@bp.route('/.well-known/webfinger')
def webfinger():
    if request.args.get('resource'):
        query = request.args.get('resource')  # acct:alice@tada.club
        if 'acct:' in query:
            actor = query.split(':')[1].split('@')[0]  # alice
        elif 'https:' in query or 'http:' in query:
            actor = query.split('/')[-1]
        else:
            return 'Webfinger regex failed to match'

        # special case: instance actor
        if actor == current_app.config['SERVER_NAME']:
            webfinger_data = {
              "subject": f"acct:{actor}@{current_app.config['SERVER_NAME']}",
              "aliases": [f"https://{current_app.config['SERVER_NAME']}/actor"],
              "links": [
                {
                    "rel": "http://webfinger.net/rel/profile-page",
                    "type": "text/html",
                    "href": f"https://{current_app.config['SERVER_NAME']}/about"
                },
                {
                    "rel": "self",
                    "type": "application/activity+json",
                    "href": f"https://{current_app.config['SERVER_NAME']}/actor",
                }
              ]
            }
            resp = jsonify(webfinger_data)
            resp.headers.add_header('Access-Control-Allow-Origin', '*')
            return resp

        seperator = 'u'
        type = 'Person'
        user = User.query.filter(or_(User.user_name == actor.strip(), User.alt_user_name == actor.strip())).filter_by(deleted=False, banned=False, ap_id=None).first()
        if user is None:
            community = Community.query.filter_by(name=actor.strip(), ap_id=None).first()
            if community is None:
                return ''
            seperator = 'c'
            type = 'Group'

        webfinger_data = {
            "subject": f"acct:{actor}@{current_app.config['SERVER_NAME']}",
            "aliases": [f"https://{current_app.config['SERVER_NAME']}/{seperator}/{actor}"],
            "links": [
                {
                    "rel": "http://webfinger.net/rel/profile-page",
                    "type": "text/html",
                    "href": f"https://{current_app.config['SERVER_NAME']}/{seperator}/{actor}"
                },
                {
                    "rel": "self",
                    "type": "application/activity+json",
                    "href": f"https://{current_app.config['SERVER_NAME']}/{seperator}/{actor}",
                    "properties": {
                        "https://www.w3.org/ns/activitystreams#type": type
                    }
                }
            ]
        }
        resp = jsonify(webfinger_data)
        resp.headers.add_header('Access-Control-Allow-Origin', '*')
        return resp
    else:
        abort(404)


@bp.route('/.well-known/nodeinfo')
@cache.cached(timeout=600)
def nodeinfo():
    nodeinfo_data = {"links": [{"rel": "http://nodeinfo.diaspora.software/ns/schema/2.0",
                                "href": f"https://{current_app.config['SERVER_NAME']}/nodeinfo/2.0"},
                                {"rel": "https://www.w3.org/ns/activitystreams#Application",
                                 "href": f"https://{current_app.config['SERVER_NAME']}"}]}
    return jsonify(nodeinfo_data)


@bp.route('/.well-known/host-meta')
@cache.cached(timeout=600)
def host_meta():
    resp = make_response('<?xml version="1.0" encoding="UTF-8"?>\n<XRD xmlns="http://docs.oasis-open.org/ns/xri/xrd-1.0">\n<Link rel="lrdd" template="https://' + current_app.config["SERVER_NAME"] + '/.well-known/webfinger?resource={uri}"/>\n</XRD>')
    resp.content_type = 'application/xrd+xml; charset=utf-8'
    return resp


@bp.route('/nodeinfo/2.0')
@bp.route('/nodeinfo/2.0.json')
@cache.cached(timeout=600)
def nodeinfo2():

    nodeinfo_data = {
                "version": "2.0",
                "software": {
                    "name": "PieFed",
                    "version": "0.1"
                },
                "protocols": [
                    "activitypub"
                ],
                "usage": {
                    "users": {
                        "total": users_total(),
                        "activeHalfyear": active_half_year(),
                        "activeMonth": active_month()
                    },
                    "localPosts": local_posts(),
                    "localComments": local_comments()
                },
                "openRegistrations": g.site.registration_mode != 'Closed'
            }
    return jsonify(nodeinfo_data)


@bp.route('/api/v1/instance')
@cache.cached(timeout=600)
def api_v1_instance():
    retval = {
        'title': g.site.name,
        'uri': current_app.config['SERVER_NAME'],
        'stats': {
            "user_count": users_total(),
            "status_count": local_posts() + local_comments(),
            "domain_count": 1
        },
        'registrations': g.site.registration_mode != 'Closed',
        'approval_required': g.site.registration_mode == 'RequireApplication'
    }
    return jsonify(retval)


@bp.route('/api/v1/instance/domain_blocks')
@cache.cached(timeout=600)
def domain_blocks():
    use_allowlist = get_setting('use_allowlist', False)
    if use_allowlist:
        return jsonify([])
    else:
        retval = []
        for domain in BannedInstances.query.all():
            retval.append({
                'domain': domain.domain,
                'digest': sha256_digest(domain.domain),
                'severity': 'suspend',
                'comment': domain.reason if domain.reason else ''
            })
    return jsonify(retval)


@bp.route('/api/v3/site')
@cache.cached(timeout=600)
def lemmy_site():
    return jsonify(lemmy_site_data())


@bp.route('/api/v3/federated_instances')
@cache.cached(timeout=600)
def lemmy_federated_instances():
    instances = Instance.query.filter(Instance.id != 1).all()
    linked = []
    allowed = []
    blocked = []
    for instance in AllowedInstances.query.all():
        allowed.append({"id": instance.id, "domain": instance.domain, "published": utcnow(), "updated": utcnow()})
    for instance in BannedInstances.query.all():
        blocked.append({"id": instance.id, "domain": instance.domain, "published": utcnow(), "updated": utcnow()})
    for instance in instances:
        instance_data = {"id": instance.id, "domain": instance.domain, "published": instance.created_at.isoformat(), "updated": instance.updated_at.isoformat()}
        if instance.software:
            instance_data['software'] = instance.software
        if instance.version:
            instance_data['version'] = instance.version
        if not any(blocked_instance.get('domain') == instance.domain for blocked_instance in blocked):
            linked.append(instance_data)
    return jsonify({
        "federated_instances": {
            "linked": linked,
            "allowed": allowed,
            "blocked": blocked
        }
    })


@bp.route('/u/<actor>', methods=['GET', 'HEAD'])
def user_profile(actor):
    """ Requests to this endpoint can be for a JSON representation of the user, or a HTML rendering of their profile.
    The two types of requests are differentiated by the header """
    actor = actor.strip()
    # admins can view deleted accounts
    if current_user.is_authenticated and current_user.is_admin():
        if '@' in actor:
            user: User = User.query.filter_by(ap_id=actor.lower()).first()
        else:
            user: User = User.query.filter(or_(User.user_name == actor, User.alt_user_name == actor)).filter_by(ap_id=None).first()
            if user is None:
                user = User.query.filter_by(ap_profile_id=f'https://{current_app.config["SERVER_NAME"]}/u/{actor.lower()}', deleted=False, ap_id=None).first()
    else:
        if '@' in actor:
            user: User = User.query.filter_by(ap_id=actor.lower(), deleted=False, banned=False).first()
        else:
            user: User = User.query.filter(or_(User.user_name == actor, User.alt_user_name == actor)).filter_by(deleted=False, ap_id=None).first()
            if user is None:
                user = User.query.filter_by(ap_profile_id=f'https://{current_app.config["SERVER_NAME"]}/u/{actor.lower()}', deleted=False, ap_id=None).first()

    if user is not None:
        main_user_name = True
        if user.alt_user_name == actor:
            main_user_name = False
        if request.method == 'HEAD':
            if is_activitypub_request():
                resp = jsonify('')
                resp.content_type = 'application/activity+json'
                return resp
            else:
                return ''
        if is_activitypub_request():
            server = current_app.config['SERVER_NAME']
            actor_data = {  "@context": default_context(),
                            "type": "Person" if not user.bot else "Service",
                            "id": user.public_url(main_user_name),
                            "preferredUsername": actor,
                            "name": user.title if user.title else user.user_name,
                            "inbox": f"{user.public_url(main_user_name)}/inbox",
                            "outbox": f"{user.public_url(main_user_name)}/outbox",
                            "discoverable": user.searchable,
                            "indexable": user.indexable,
                            "manuallyApprovesFollowers": False if not user.ap_manually_approves_followers else user.ap_manually_approves_followers,
                            "publicKey": {
                                "id": f"{user.public_url(main_user_name)}#main-key",
                                "owner": user.public_url(main_user_name),
                                "publicKeyPem": user.public_key
                            },
                            "endpoints": {
                                "sharedInbox": f"https://{server}/inbox"
                            },
                            "published": ap_datetime(user.created),
                        }
            if not main_user_name:
                actor_data['name'] = 'Anonymous'
                actor_data['published'] = ap_datetime(user.created + timedelta(minutes=randint(-2592000, 0)))
                actor_data['summary'] = '<p>This is an anonymous alternative account of another account. It has been generated automatically for a Piefed user who chose to keep their interactions private. They cannot reply to your messages using this account, but only upvote (like) or downvote (dislike). For more information about Piefed and this feature see <a href="https://piefed.social/post/205362">https://piefed.social/post/205362</a>.</p>'
            if user.avatar_id is not None and main_user_name:
                actor_data["icon"] = {
                    "type": "Image",
                    "url": f"https://{current_app.config['SERVER_NAME']}{user.avatar_image()}"
                }
            if user.cover_id is not None and main_user_name:
                actor_data["image"] = {
                    "type": "Image",
                    "url": f"https://{current_app.config['SERVER_NAME']}{user.cover_image()}"
                }
            if user.about_html and main_user_name:
                actor_data['summary'] = user.about_html
                actor_data['source'] = {'content': user.about, 'mediaType': 'text/markdown'}
            if user.matrix_user_id and main_user_name:
                actor_data['matrixUserId'] = user.matrix_user_id
            if user.extra_fields.count() > 0:
                actor_data['attachment'] = []
                for field in user.extra_fields:
                    actor_data['attachment'].append({'type': 'PropertyValue',
                                                     'name': field.label,
                                                     'value': field.text})
            resp = jsonify(actor_data)
            resp.content_type = 'application/activity+json'
            resp.headers.set('Link', f'<https://{current_app.config["SERVER_NAME"]}/u/{actor}>; rel="alternate"; type="text/html"')
            return resp
        else:
            if main_user_name:
                return show_profile(user)
            else:
                return render_template('errors/alt_profile.html')
    else:
        abort(404)


@bp.route('/u/<actor>/outbox', methods=['GET'])
def user_outbox(actor):
    outbox = {
        "@context": default_context(),
        'type': 'OrderedCollection',
        'id': f"https://{current_app.config['SERVER_NAME']}/u/{actor}/outbox",
        'orderedItems': [],
        'totalItems': 0
    }
    resp = jsonify(outbox)
    resp.content_type = 'application/activity+json'
    return resp


@bp.route('/c/<actor>', methods=['GET'])
def community_profile(actor):
    """ Requests to this endpoint can be for a JSON representation of the community, or a HTML rendering of it.
        The two types of requests are differentiated by the header """
    actor = actor.strip()
    if '@' in actor:
        # don't provide activitypub info for remote communities
        if 'application/ld+json' in request.headers.get('Accept', '') or 'application/activity+json' in request.headers.get('Accept', ''):
            abort(400)
        community: Community = Community.query.filter_by(ap_id=actor.lower(), banned=False).first()
    else:
        community: Community = Community.query.filter_by(name=actor, ap_id=None).first()
    if community is not None:
        if is_activitypub_request():
            server = current_app.config['SERVER_NAME']
            actor_data = {"@context": default_context(),
                "type": "Group",
                "id": f"https://{server}/c/{actor}",
                "name": community.title,
                "sensitive": True if community.nsfw or community.nsfl else False,
                "preferredUsername": actor,
                "inbox": f"https://{server}/c/{actor}/inbox",
                "outbox": f"https://{server}/c/{actor}/outbox",
                "followers": f"https://{server}/c/{actor}/followers",
                "moderators": f"https://{server}/c/{actor}/moderators",
                "featured": f"https://{server}/c/{actor}/featured",
                "attributedTo": f"https://{server}/c/{actor}/moderators",
                "postingRestrictedToMods": community.restricted_to_mods or community.local_only,
                "newModsWanted": community.new_mods_wanted,
                "privateMods": community.private_mods,
                "url": f"https://{server}/c/{actor}",
                "publicKey": {
                    "id": f"https://{server}/c/{actor}#main-key",
                    "owner": f"https://{server}/c/{actor}",
                    "publicKeyPem": community.public_key
                },
                "endpoints": {
                    "sharedInbox": f"https://{server}/inbox"
                },
                "published": ap_datetime(community.created_at),
                "updated": ap_datetime(community.last_active),
            }
            if community.description_html:
                actor_data["summary"] = community.description_html
                actor_data['source'] = {'content': community.description, 'mediaType': 'text/markdown'}
            if community.icon_id is not None:
                actor_data["icon"] = {
                    "type": "Image",
                    "url": f"https://{current_app.config['SERVER_NAME']}{community.icon_image()}"
                }
            if community.image_id is not None:
                actor_data["image"] = {
                    "type": "Image",
                    "url": f"https://{current_app.config['SERVER_NAME']}{community.header_image()}"
                }
            resp = jsonify(actor_data)
            resp.content_type = 'application/activity+json'
            resp.headers.set('Link', f'<https://{current_app.config["SERVER_NAME"]}/c/{actor}>; rel="alternate"; type="text/html"')
            return resp
        else:   # browser request - return html
            return show_community(community)
    else:
        abort(404)


@bp.route('/inbox', methods=['POST'])
def shared_inbox():
    try:
        request_json = request.get_json(force=True)
    except werkzeug.exceptions.BadRequest as e:
        log_incoming_ap('', APLOG_NOTYPE, APLOG_FAILURE, None, 'Unable to parse json body: ' + e.description)
        return '', 200

    g.site = Site.query.get(1)                      # g.site is not initialized by @app.before_request when request.path == '/inbox'
    store_ap_json = g.site.log_activitypub_json

    if not 'id' in request_json or not 'type' in request_json or not 'actor' in request_json or not 'object' in request_json:
        log_incoming_ap('', APLOG_NOTYPE, APLOG_FAILURE, request_json if store_ap_json else None, 'Missing minimum expected fields in JSON')
        return '', 200

    id = request_json['id']
    if request_json['type'] == 'Announce' and isinstance(request_json['object'], dict):
        object = request_json['object']
        if not 'id' in object or not 'type' in object or not 'actor' in object or not 'object' in object:
            if 'type' in object and (object['type'] == 'Page' or object['type'] == 'Note'):
                log_incoming_ap(id, APLOG_ANNOUNCE, APLOG_IGNORED, request_json if store_ap_json else None, 'Intended for Mastodon')
            else:
                log_incoming_ap(id, APLOG_ANNOUNCE, APLOG_FAILURE, request_json if store_ap_json else None, 'Missing minimum expected fields in JSON Announce object')
            return '', 200

        if isinstance(object['actor'], str) and object['actor'].startswith('https://' + current_app.config['SERVER_NAME']):
            log_incoming_ap(id, APLOG_DUPLICATE, APLOG_IGNORED, request_json if store_ap_json else None, 'Activity about local content which is already present')
            return '', 200

    redis_client = get_redis_connection()
    if redis_client.exists(id):                 # Something is sending same activity multiple times
        log_incoming_ap(id, APLOG_DUPLICATE, APLOG_IGNORED, request_json if store_ap_json else None, 'Unnecessary retry attempt')
        return '', 200
    redis_client.set(id, 1, ex=90)              # Save the activity ID into redis, to avoid duplicate activities

    # Ignore unutilised PeerTube activity
    if isinstance(request_json['actor'], str) and request_json['actor'].endswith('accounts/peertube'):
        log_incoming_ap(id, APLOG_PT_VIEW, APLOG_IGNORED, request_json if store_ap_json else None, 'PeerTube View or CacheFile activity')
        return ''

    # Ignore account deletion requests from users that do not already exist here
    account_deletion = False
    if (request_json['type'] == 'Delete' and
        'object' in request_json and isinstance(request_json['object'], str) and
        request_json['actor'] == request_json['object']):
        account_deletion = True
        actor = User.query.filter_by(ap_profile_id=request_json['actor'].lower()).first()
        if not actor:
            log_incoming_ap(id, APLOG_DELETE, APLOG_IGNORED, request_json if store_ap_json else None, 'Does not exist here')
            return '', 200
    else:
        actor = find_actor_or_create(request_json['actor'])

    if not actor:
        actor_name = request_json['actor']
        log_incoming_ap(id, APLOG_NOTYPE, APLOG_FAILURE, request_json if store_ap_json else None, f'Actor could not be found 1: {actor_name}')
        return '', 200

    if actor.is_local():        # should be impossible (can be Announced back, but not sent without access to privkey)
        log_incoming_ap(id, APLOG_NOTYPE, APLOG_FAILURE, request_json if store_ap_json else None, 'ActivityPub activity from a local actor')
        return '', 200

    bounced = False
    try:
        HttpSignature.verify_request(request, actor.public_key, skip_date=True)
    except VerificationError as e:
        bounced = True
        if not 'signature' in request_json:
            log_incoming_ap(id, APLOG_NOTYPE, APLOG_FAILURE, request_json if store_ap_json else None, 'Could not verify HTTP signature: ' + str(e))
            return '', 400
        # HTTP sig will fail if a.gup.pe or PeerTube have bounced a request, so check LD sig instead
        try:
            LDSignature.verify_signature(request_json, actor.public_key)
        except VerificationError as e:
            log_incoming_ap(id, APLOG_NOTYPE, APLOG_FAILURE, request_json if store_ap_json else None, 'Could not verify LD signature: ' + str(e))
            return '', 400

    actor.instance.last_seen = utcnow()
    actor.instance.dormant = False
    actor.instance.gone_forever = False
    actor.instance.failures = 0
    actor.instance.ip_address = ip_address() if not bounced else ''
    db.session.commit()

    # When a user is deleted, the only way to be fairly sure they get deleted everywhere is to tell the whole fediverse.
    # Earlier check means this is only for users that already exist, processing it here means that http signature will have been verified
    if account_deletion == True:
        if current_app.debug:
            process_delete_request(request_json, store_ap_json)
        else:
            process_delete_request.delay(request_json, store_ap_json)
        return ''

    if current_app.debug:
        process_inbox_request(request_json, store_ap_json)
    else:
        process_inbox_request.delay(request_json, store_ap_json)

    return ''


@bp.route('/site_inbox', methods=['POST'])
def site_inbox():
    return shared_inbox()


@bp.route('/u/<actor>/inbox', methods=['POST'])
def user_inbox(actor):
    return shared_inbox()


@bp.route('/c/<actor>/inbox', methods=['POST'])
def community_inbox(actor):
    return shared_inbox()


def replay_inbox_request(request_json):
    if not 'id' in request_json or not 'type' in request_json or not 'actor' in request_json or not 'object' in request_json:
        log_incoming_ap('', APLOG_NOTYPE, APLOG_FAILURE, request_json, 'REPLAY: Missing minimum expected fields in JSON')
        return

    id = request_json['id']
    if request_json['type'] == 'Announce' and isinstance(request_json['object'], dict):
        object = request_json['object']
        if not 'id' in object or not 'type' in object or not 'actor' in object or not 'object' in object:
            if 'type' in object and (object['type'] == 'Page' or object['type'] == 'Note'):
                log_incoming_ap(id, APLOG_ANNOUNCE, APLOG_IGNORED, request_json, 'REPLAY: Intended for Mastodon')
            else:
                log_incoming_ap(id, APLOG_ANNOUNCE, APLOG_FAILURE, request_json, 'REPLAY: Missing minimum expected fields in JSON Announce object')
            return

        if isinstance(object['actor'], str) and object['actor'].startswith('https://' + current_app.config['SERVER_NAME']):
            log_incoming_ap(id, APLOG_DUPLICATE, APLOG_IGNORED, request_json if store_ap_json else None, 'Activity about local content which is already present')
            return

    # Ignore unutilised PeerTube activity
    if isinstance(request_json['actor'], str) and request_json['actor'].endswith('accounts/peertube'):
        log_incoming_ap(id, APLOG_PT_VIEW, APLOG_IGNORED, request_json, 'REPLAY: PeerTube View or CacheFile activity')
        return

    # Ignore account deletion requests from users that do not already exist here
    account_deletion = False
    if (request_json['type'] == 'Delete' and
        'object' in request_json and isinstance(request_json['object'], str) and
        request_json['actor'] == request_json['object']):
        account_deletion = True
        actor = User.query.filter_by(ap_profile_id=request_json['actor'].lower()).first()
        if not actor:
            log_incoming_ap(id, APLOG_DELETE, APLOG_IGNORED, request_json, 'REPLAY: Does not exist here')
            return
    else:
        actor = find_actor_or_create(request_json['actor'])

    if not actor:
        actor_name = request_json['actor']
        log_incoming_ap(id, APLOG_NOTYPE, APLOG_FAILURE, request_json, f'REPLAY: Actor could not be found 1: {actor_name}')
        return

    if actor.is_local():        # should be impossible (can be Announced back, but not sent back without access to privkey)
        log_incoming_ap(id, APLOG_NOTYPE, APLOG_FAILURE, request_json, 'REPLAY: ActivityPub activity from a local actor')
        return

    # When a user is deleted, the only way to be fairly sure they get deleted everywhere is to tell the whole fediverse.
    if account_deletion == True:
        process_delete_request(request_json, True)
        return

    process_inbox_request(request_json, True)

    return


@celery.task
def process_inbox_request(request_json, store_ap_json):
    with current_app.app_context():
        site = Site.query.get(1)    # can't use g.site because celery doesn't use Flask's g variable

        # For an Announce, Accept, or Reject, we have the community, and need to find the user
        # For everything else, we have the user, and need to find the community
        # Benefits of always using request_json['actor']:
        #   It's the actor who signed the request, and whose signature has been verified
        #   Because of the earlier check, we know that they already exist, and so don't need to check again
        #   Using actors from inner objects has a vulnerability to spoofing attacks (e.g. if 'attributedTo' doesn't match the 'Create' actor)
        id = request_json['id']
        if request_json['type'] == 'Announce' or request_json['type'] == 'Accept' or request_json['type'] == 'Reject':
            community_ap_id = request_json['actor']
            community = find_actor_or_create(community_ap_id, community_only=True, create_if_not_found=False)
            if not community or not isinstance(community, Community):
                log_incoming_ap(id, APLOG_ANNOUNCE, APLOG_FAILURE, request_json, 'Actor was not a community')
                return
            user_ap_id = None               # found in 'if request_json['type'] == 'Announce', or it's a local user (for 'Accept'/'Reject')
        else:
            user_ap_id = request_json['actor']
            user = find_actor_or_create(user_ap_id, create_if_not_found=False)
            if not user or not isinstance(user, User):
                log_incoming_ap(id, APLOG_NOTYPE, APLOG_FAILURE, request_json, 'Actor was not a user')
                return
            user.last_seen = site.last_active = utcnow()
            db.session.commit()
            community = None                # found as needed

        # Follow: remote user wants to join/follow one of our users or communities
        if request_json['type'] == 'Follow':
            target_ap_id = request_json['object']
            follow_id = request_json['id']
            target = find_actor_or_create(target_ap_id, create_if_not_found=False)
            if not target:
                log_incoming_ap(id, APLOG_FOLLOW, APLOG_FAILURE, request_json if store_ap_json else None, 'Could not find target of Follow')
                return
            if isinstance(target, Community):
                community = target
                reject_follow = False
                if community.local_only:
                    log_incoming_ap(id, APLOG_FOLLOW, APLOG_FAILURE, request_json if store_ap_json else None, 'Local only cannot be followed by remote users')
                    reject_follow = True
                else:
                    # check if user is banned from this community
                    user_banned = CommunityBan.query.filter_by(user_id=user.id, community_id=community.id).first()
                    if user_banned:
                        log_incoming_ap(id, APLOG_FOLLOW, APLOG_FAILURE, request_json if store_ap_json else None, 'Remote user has been banned')
                        reject_follow = True
                if reject_follow:
                    # send reject message to deny the follow
                    reject = {"@context": default_context(), "actor": community.public_url(), "to": [user.public_url()],
                              "object": {"actor": user.public_url(), "to": None, "object": community.public_url(), "type": "Follow", "id": follow_id},
                              "type": "Reject", "id": f"https://{current_app.config['SERVER_NAME']}/activities/reject/" + gibberish(32)}
                    post_request(user.ap_inbox_url, reject, community.private_key, f"{community.public_url()}#main-key")
                else:
                    if community_membership(user, community) != SUBSCRIPTION_MEMBER:
                        member = CommunityMember(user_id=user.id, community_id=community.id)
                        db.session.add(member)
                        db.session.commit()
                        cache.delete_memoized(community_membership, user, community)
                        # send accept message to acknowledge the follow
                        accept = {"@context": default_context(), "actor": community.public_url(), "to": [user.public_url()],
                                  "object": {"actor": user.public_url(), "to": None, "object": community.public_url(), "type": "Follow", "id": follow_id},
                                  "type": "Accept", "id": f"https://{current_app.config['SERVER_NAME']}/activities/accept/" + gibberish(32)}
                        post_request(user.ap_inbox_url, accept, community.private_key, f"{community.public_url()}#main-key")
                        log_incoming_ap(id, APLOG_FOLLOW, APLOG_SUCCESS, request_json if store_ap_json else None)
                return
            elif isinstance(target, User):
                local_user = target
                remote_user = user
                if not local_user.is_local():
                    log_incoming_ap(id, APLOG_FOLLOW, APLOG_FAILURE, request_json if store_ap_json else None, 'Follow request for remote user received')
                    return
                existing_follower = UserFollower.query.filter_by(local_user_id=local_user.id, remote_user_id=remote_user.id).first()
                if not existing_follower:
                    auto_accept = not local_user.ap_manually_approves_followers
                    new_follower = UserFollower(local_user_id=local_user.id, remote_user_id=remote_user.id, is_accepted=auto_accept)
                    if not local_user.ap_followers_url:
                        local_user.ap_followers_url = local_user.public_url() + '/followers'
                    db.session.add(new_follower)
                    db.session.commit()
                    accept = {"@context": default_context(), "actor": local_user.public_url(), "to": [remote_user.public_url()],
                              "object": {"actor": remote_user.public_url(), "to": None, "object": local_user.public_url(), "type": "Follow", "id": follow_id},
                              "type": "Accept", "id": f"https://{current_app.config['SERVER_NAME']}/activities/accept/" + gibberish(32)}
                    post_request(remote_user.ap_inbox_url, accept, local_user.private_key, f"{local_user.public_url()}#main-key")
                    log_incoming_ap(id, APLOG_FOLLOW, APLOG_SUCCESS, request_json if store_ap_json else None)
            return

        # Accept: remote server is accepting our previous follow request
        if request_json['type'] == 'Accept':
            user = None
            if isinstance(request_json['object'], str): # a.gup.pe accepts using a string with the ID of the follow request
                join_request_parts = request_json['object'].split('/')
                join_request = CommunityJoinRequest.query.get(join_request_parts[-1])
                if join_request:
                    user = User.query.get(join_request.user_id)
            elif request_json['object']['type'] == 'Follow':
                user_ap_id = request_json['object']['actor']
                user = find_actor_or_create(user_ap_id, create_if_not_found=False)
            if not user:
                log_incoming_ap(id, APLOG_ACCEPT, APLOG_FAILURE, request_json if store_ap_json else None, 'Could not find recipient of Accept')
                return
            join_request = CommunityJoinRequest.query.filter_by(user_id=user.id, community_id=community.id).first()
            if join_request:
                existing_membership = CommunityMember.query.filter_by(user_id=join_request.user_id, community_id=join_request.community_id).first()
                if not existing_membership:
                    member = CommunityMember(user_id=join_request.user_id, community_id=join_request.community_id)
                    db.session.add(member)
                    community.subscriptions_count += 1
                    db.session.commit()
                    cache.delete_memoized(community_membership, user, community)
                log_incoming_ap(id, APLOG_ACCEPT, APLOG_SUCCESS, request_json if store_ap_json else None)
            return

        # Reject: remote server is rejecting our previous follow request
        if request_json['type'] == 'Reject':
            if request_json['object']['type'] == 'Follow':
                user_ap_id = request_json['object']['actor']
                user = find_actor_or_create(user_ap_id, create_if_not_found=False)
                if not user:
                    log_incoming_ap(id, APLOG_ACCEPT, APLOG_FAILURE, request_json if store_ap_json else None, 'Could not find recipient of Reject')
                    return
                join_request = CommunityJoinRequest.query.filter_by(user_id=user.id, community_id=community.id).first()
                if join_request:
                    db.session.delete(join_request)
                existing_membership = CommunityMember.query.filter_by(user_id=user.id, community_id=community.id).first()
                if existing_membership:
                    db.session.delete(existing_membership)
                    cache.delete_memoized(community_membership, user, community)
                db.session.commit()
                log_incoming_ap(id, APLOG_ACCEPT, APLOG_SUCCESS, request_json if store_ap_json else None)
            return

        # Create is new content. Update is often an edit, but Updates from Lemmy can also be new content
        if request_json['type'] == 'Create' or request_json['type'] == 'Update':
            if request_json['object']['type'] == 'ChatMessage':
                sender = user
                recipient_ap_id = request_json['object']['to'][0]
                recipient = find_actor_or_create(recipient_ap_id, create_if_not_found=False)
                if recipient and recipient.is_local():
                    if sender.created_recently() or sender.reputation <= -10:
                        log_incoming_ap(id, APLOG_CHATMESSAGE, APLOG_FAILURE, request_json if store_ap_json else None, 'Sender not eligible to send')
                        return
                    elif recipient.has_blocked_user(sender.id) or recipient.has_blocked_instance(sender.instance_id):
                        log_incoming_ap(id, APLOG_CHATMESSAGE, APLOG_FAILURE, request_json if store_ap_json else None, 'Sender blocked by recipient')
                        return
                    else:
                        # Find existing conversation to add to
                        existing_conversation = Conversation.find_existing_conversation(recipient=recipient, sender=sender)
                        if not existing_conversation:
                            existing_conversation = Conversation(user_id=sender.id)
                            existing_conversation.members.append(recipient)
                            existing_conversation.members.append(sender)
                            db.session.add(existing_conversation)
                            db.session.commit()
                        # Save ChatMessage to DB
                        encrypted = request_json['object']['encrypted'] if 'encrypted' in request_json['object'] else None
                        new_message = ChatMessage(sender_id=sender.id, recipient_id=recipient.id, conversation_id=existing_conversation.id,
                                                  body_html=request_json['object']['content'],
                                                  body=html_to_text(request_json['object']['content']),
                                                  encrypted=encrypted)
                        db.session.add(new_message)
                        existing_conversation.updated_at = utcnow()
                        db.session.commit()

                        # Notify recipient
                        notify = Notification(title=shorten_string('New message from ' + sender.display_name()),
                                              url=f'/chat/{existing_conversation.id}#message_{new_message}', user_id=recipient.id,
                                              author_id=sender.id)
                        db.session.add(notify)
                        recipient.unread_notifications += 1
                        existing_conversation.read = False
                        db.session.commit()
                        log_incoming_ap(id, APLOG_CHATMESSAGE, APLOG_SUCCESS, request_json if store_ap_json else None)
                return
            # inner object of Create is not a ChatMessage
            else:
                if (request_json['object']['type'] == 'Note' and 'name' in request_json['object'] and                           # Poll Votes
                    'inReplyTo' in request_json['object'] and 'attributedTo' in request_json['object']):
                    post_being_replied_to = Post.query.filter_by(ap_id=request_json['object']['inReplyTo']).first()
                    if post_being_replied_to:
                        poll_data = Poll.query.get(post_being_replied_to.id)
                        choice = PollChoice.query.filter_by(post_id=post_being_replied_to.id, choice_text=request_json['object']['name']).first()
                        if poll_data and choice:
                            poll_data.vote_for_choice(choice.id, user.id)
                            db.session.commit()
                            log_incoming_ap(id, APLOG_CREATE, APLOG_SUCCESS, request_json if store_ap_json else None)
                        if post_being_replied_to.author.is_local():
                            inform_followers_of_post_update(post_being_replied_to.id, user.instance_id)
                    return
                community_ap_id = find_community_ap_id(request_json)
                if not ensure_domains_match(request_json['object']):
                    log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Domains do not match')
                    return
                community = find_actor_or_create(community_ap_id, community_only=True, create_if_not_found=False) if community_ap_id else None
                if community and community.local_only:
                    log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Remote Create in local_only community')
                    return
                if not community:
                    log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Blocked or unfound community')
                    return

                object_type = request_json['object']['type']
                new_content_types = ['Page', 'Article', 'Link', 'Note', 'Question']
                if object_type in new_content_types:  # create or update a post
                    process_new_content(user, community, store_ap_json, request_json, announced=False)
                    return
                elif object_type == 'Video':  # PeerTube: editing a video (PT doesn't Announce these)
                    post = Post.query.filter_by(ap_id=request_json['object']['id']).first()
                    if post:
                        if user.id == post.user_id:
                            update_post_from_activity(post, request_json)
                            log_incoming_ap(id, APLOG_UPDATE, APLOG_SUCCESS, request_json if store_ap_json else None)
                            return
                        else:
                            log_incoming_ap(id, APLOG_UPDATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Edit attempt denied')
                            return
                    else:
                        log_incoming_ap(id, APLOG_UPDATE, APLOG_FAILURE, request_json if store_ap_json else None, 'PeerTube post not found')
                        return
                else:
                    log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Unacceptable type (create): ' + object_type)
            return

        if request_json['type'] == 'Delete':
            if isinstance(request_json['object'], str):
                ap_id = request_json['object']  # lemmy
            else:
                ap_id = request_json['object']['id']  # kbin
            to_delete = find_liked_object(ap_id)                        # Just for Posts and Replies (User deletes go through process_delete_request())

            if to_delete:
                if to_delete.deleted:
                    log_incoming_ap(id, APLOG_DELETE, APLOG_IGNORED, request_json if store_ap_json else None, 'Activity about local content which is already deleted')
                else:
                    delete_post_or_comment(user, to_delete, store_ap_json, request_json)
                    announce_activity_to_followers(to_delete.community, user, request_json)
            else:
                log_incoming_ap(id, APLOG_DELETE, APLOG_FAILURE, request_json if store_ap_json else None, 'Delete: cannot find ' + ap_id)
            return

        if request_json['type'] == 'Like' or request_json['type'] == 'EmojiReact':  # Upvote
            process_upvote(user, store_ap_json, request_json, announced=False)
            return

        if request_json['type'] == 'Dislike':  # Downvote
            if site.enable_downvotes is False:
                log_incoming_ap(id, APLOG_DISLIKE, APLOG_IGNORED, request_json if store_ap_json else None, 'Dislike ignored because of allow_dislike setting')
                return
            process_downvote(user, store_ap_json, request_json, announced=False)
            return

        if request_json['type'] == 'Flag':    # Reported content
            reported = find_reported_object(request_json['object'])
            if reported:
                process_report(user, reported, request_json)
                log_incoming_ap(id, APLOG_REPORT, APLOG_SUCCESS, request_json if store_ap_json else None)
                announce_activity_to_followers(reported.community, user, request_json)
            else:
                log_incoming_ap(id, APLOG_REPORT, APLOG_IGNORED, request_json if store_ap_json else None, 'Report ignored due to missing content')
            return

        if request_json['type'] == 'Add':       # remote site is adding a local user as a moderator, and is sending directly rather than announcing (happens if not subscribed)
            mod = user
            community_ap_id = find_community_ap_id(request_json)
            community = find_actor_or_create(community_ap_id, community_only=True, create_if_not_found=False) if community_ap_id else None
            if community:
                if not community.is_moderator(mod) and not community.is_instance_admin(mod):
                    log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Does not have permission')
                    return
                target = request_json['target']
                moderators_url = community.ap_moderators_url
                if target == moderators_url:
                    new_mod = find_actor_or_create(request_json['object'], create_if_not_found=False)
                    if new_mod and new_mod.is_local():
                        existing_membership = CommunityMember.query.filter_by(community_id=community.id, user_id=new_mod.id).first()
                        if existing_membership:
                            existing_membership.is_moderator = True
                        else:
                            new_membership = CommunityMember(community_id=community.id, user_id=new_mod.id, is_moderator=True)
                            db.session.add(new_membership)
                        db.session.commit()
                        log_incoming_ap(id, APLOG_ADD, APLOG_SUCCESS, request_json if store_ap_json else None)
                    else:
                        log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Cannot find: ' + request_json['object'])
                    return
                else:
                    # Lemmy might not send anything directly to sticky a post if no-one is subscribed (could not get it to generate the activity)
                    log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Unknown target for Add')
            else:
                log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Add: cannot find community')
            return

        if request_json['type'] == 'Remove':       # remote site is removing a local user as a moderator, and is sending directly rather than announcing (happens if not subscribed)
            mod = user
            community_ap_id = find_community_ap_id(request_json)
            community = find_actor_or_create(community_ap_id, community_only=True, create_if_not_found=False) if community_ap_id else None
            if community:
                if not community.is_moderator(mod) and not community.is_instance_admin(mod):
                    log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Does not have permission')
                    return
                target = request_json['target']
                moderators_url = community.ap_moderators_url
                if target == moderators_url:
                    old_mod = find_actor_or_create(request_json['object'], create_if_not_found=False)
                    if old_mod and old_mod.is_local():
                        existing_membership = CommunityMember.query.filter_by(community_id=community.id, user_id=old_mod.id).first()
                        if existing_membership:
                            existing_membership.is_moderator = False
                            db.session.commit()
                            log_incoming_ap(id, APLOG_REMOVE, APLOG_SUCCESS, request_json if store_ap_json else None)
                    else:
                        log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Cannot find: ' + request_json['object'])
                    return
                else:
                    # Lemmy might not send anything directly to unsticky a post if no-one is subscribed (could not get it to generate the activity)
                    log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Unknown target for Remove')
            else:
                log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Remove: cannot find community')
            return

        if request_json['type'] == 'Block':     # remote site is banning one of their users
            blocker = user
            blocked_ap_id = request_json['object'].lower()
            blocked = User.query.filter_by(ap_profile_id=blocked_ap_id).first()
            if store_ap_json:
                request_json['cc'] = []                                         # cut very long list of instances
            if not blocked:
                log_incoming_ap(id, APLOG_USERBAN, APLOG_IGNORED, request_json if store_ap_json else None, 'Does not exist here')
                return

            # target = request_json['target']   # target is supposed to determine the scope - whether it is an instance-wide ban or just one community. Lemmy doesn't use it right though
            # community = find_actor_or_create(target, create_if_not_found=False, community_only=True)

            remove_data = request_json['removeData'] if 'removeData' in request_json else False

            # Lemmy currently only sends userbans for admins banning local users
            # Banning remote users is hacked by banning them from every community of which they are a part
            # There's plans to change this in the future though.
            if not blocker.is_instance_admin() or not blocked.instance_id == blocker.instance_id:
                log_incoming_ap(id, APLOG_USERBAN, APLOG_FAILURE, request_json if store_ap_json else None, 'Does not have permission')
                return

            if blocked.banned:  # We may have already banned them - we don't want remote temp bans to over-ride our permanent bans
                return

            if blocked.is_local():  # Sanity check
                current_app.logger.error('Attempt to ban local user: ' + str(request_json))
                return

            blocked.banned = True
            db.session.commit()
            if 'expires' in request_json:
                blocked.banned_until = request_json['expires']
            elif 'endTime' in request_json:
                blocked.banned_until = request_json['endTime']
            try:
                db.session.commit()
            except:  # I don't know the format of expires or endTime so let's see how this goes
                db.session.rollback()
                current_app.logger.error('could not save banned_until value: ' + str(request_json))

            if remove_data:
                site_ban_remove_data(blocker.id, blocked)
                log_incoming_ap(id, APLOG_USERBAN, APLOG_SUCCESS, request_json if store_ap_json else None)
            else:
                log_incoming_ap(id, APLOG_USERBAN, APLOG_IGNORED, request_json if store_ap_json else None, 'Banned, but content retained')

            return

        if request_json['type'] == 'Undo':
            if request_json['object']['type'] == 'Follow':                      # Unsubscribe from a community or user
                target_ap_id = request_json['object']['object']
                target = find_actor_or_create(target_ap_id, create_if_not_found=False)
                if isinstance(target, Community):
                    community = target
                    member = CommunityMember.query.filter_by(user_id=user.id, community_id=community.id).first()
                    join_request = CommunityJoinRequest.query.filter_by(user_id=user.id, community_id=community.id).first()
                    if member:
                        db.session.delete(member)
                        community.subscriptions_count -= 1
                    if join_request:
                        db.session.delete(join_request)
                    db.session.commit()
                    cache.delete_memoized(community_membership, user, community)
                    log_incoming_ap(id, APLOG_UNDO_FOLLOW, APLOG_SUCCESS, request_json if store_ap_json else None)
                    return
                if isinstance(target, User):
                    local_user = target
                    remote_user = user
                    follower = UserFollower.query.filter_by(local_user_id=local_user.id, remote_user_id=remote_user.id, is_accepted=True).first()
                    if follower:
                        db.session.delete(follower)
                        db.session.commit()
                        log_incoming_ap(id, APLOG_UNDO_FOLLOW, APLOG_SUCCESS, request_json if store_ap_json else None)
                    return
                if not target:
                    log_incoming_ap(id, APLOG_UNDO_FOLLOW, APLOG_FAILURE, request_json if store_ap_json else None, 'Unfound target')
                return

            if request_json['object']['type'] == 'Delete':                      # Restore something previously deleted
                if isinstance(request_json['object']['object'], str):
                    ap_id = request_json['object']['object']  # lemmy
                else:
                    ap_id = request_json['object']['object']['id']  # kbin

                restorer = user
                to_restore = find_liked_object(ap_id)                           # a user or a mod/admin is undoing the delete of a post or reply
                if to_restore:
                    if not to_restore.deleted:
                        log_incoming_ap(id, APLOG_UNDO_DELETE, APLOG_IGNORED, request_json if store_ap_json else None, 'Activity about local content which is already restored')
                    else:
                        restore_post_or_comment(restorer, to_restore, store_ap_json, request_json)
                        announce_activity_to_followers(to_restore.community, user, request_json)
                else:
                    log_incoming_ap(id, APLOG_UNDO_DELETE, APLOG_FAILURE, request_json if store_ap_json else None, 'Undo delete: cannot find ' + ap_id)
                return

            if request_json['object']['type'] == 'Like' or request_json['object']['type'] == 'Dislike':                        # Undoing an upvote or downvote
                post = comment = None
                target_ap_id = request_json['object']['object']
                post_or_comment = undo_vote(comment, post, target_ap_id, user)
                if post_or_comment:
                    log_incoming_ap(id, APLOG_UNDO_VOTE, APLOG_SUCCESS, request_json if store_ap_json else None)
                    announce_activity_to_followers(post_or_comment.community, user, request_json)
                else:
                    log_incoming_ap(id, APLOG_UNDO_VOTE, APLOG_FAILURE, request_json if store_ap_json else None, 'Unfound object ' + target_ap_id)
                return

            if request_json['object']['type'] == 'Block':     # remote site is unbanning one of their users
                unblocker = user
                unblocked_ap_id = request_json['object']['object'].lower()
                unblocked = User.query.filter_by(ap_profile_id=unblocked_ap_id).first()
                if store_ap_json:
                    request_json['cc'] = []                                         # cut very long list of instances
                    request_json['object']['cc'] = []
                if not unblocked:
                    log_incoming_ap(id, APLOG_USERBAN, APLOG_IGNORED, request_json if store_ap_json else None, 'Does not exist here')
                    return
                unblock_from_ap_id = request_json['object']['target']

                if not unblocker.is_instance_admin() or not unblocked.instance_id == unblocker.instance_id:
                    log_incoming_ap(id, APLOG_USERBAN, APLOG_FAILURE, request_json if store_ap_json else None, 'Does not have permission')
                    return

                # (no removeData field in an undo/ban - cannot restore without knowing if deletion was part of ban, or different moderator action)
                #unblocked.banned = False                   # uncommented until there's a mechanism for processing ban expiry date
                #db.session.commit()
                log_incoming_ap(id, APLOG_UNDO_USERBAN, APLOG_SUCCESS, request_json if store_ap_json else None)
                return

        # Announce is new content and votes that happened on a remote server.
        if request_json['type'] == 'Announce':
            if isinstance(request_json['object'], str):  # Mastodon, PeerTube, A.gup.pe
                if request_json['object'].startswith('https://' + current_app.config['SERVER_NAME']):
                    log_incoming_ap(id, APLOG_DUPLICATE, APLOG_IGNORED, request_json if store_ap_json else None, 'Activity about local content which is already present')
                    return
                post = resolve_remote_post(request_json['object'], community.id, announce_actor=community.ap_profile_id, store_ap_json=store_ap_json)
                if post:
                    log_incoming_ap(id, APLOG_ANNOUNCE, APLOG_SUCCESS, request_json)
                else:
                    log_incoming_ap(id, APLOG_ANNOUNCE, APLOG_FAILURE, request_json, 'Could not resolve post')
                return

            user_ap_id = request_json['object']['actor']
            user = find_actor_or_create(user_ap_id)
            if not user or not isinstance(user, User):
                log_incoming_ap(id, APLOG_ANNOUNCE, APLOG_FAILURE, request_json if store_ap_json else None, 'Blocked or unfound user for Announce object actor ' + user_ap_id)
                return

            user.last_seen = site.last_active = utcnow()
            user.instance.last_seen = utcnow()
            user.instance.dormant = False
            user.instance.gone_forever = False
            user.instance.failures = 0
            db.session.commit()

            if request_json['object']['type'] == 'Create' or request_json['object']['type'] == 'Update':
                object_type = request_json['object']['object']['type']
                new_content_types = ['Page', 'Article', 'Link', 'Note', 'Question']
                if object_type in new_content_types:  # create or update a post
                    process_new_content(user, community, store_ap_json, request_json)
                elif request_json['object']['type'] == 'Update' and request_json['object']['object']['type'] == 'Group':
                    # force refresh next time community is heard from
                    community.ap_fetched_at = None
                    db.session.commit()
                    log_incoming_ap(id, APLOG_UPDATE, APLOG_SUCCESS, request_json if store_ap_json else None)
                else:
                    log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Unacceptable type (create): ' + object_type)
                return

            if request_json['object']['type'] == 'Delete':                                                  # Announced Delete
                if isinstance(request_json['object']['object'], str):
                    ap_id = request_json['object']['object']  # lemmy
                else:
                    ap_id = request_json['object']['object']['id']  # kbin
                to_delete = find_liked_object(ap_id)                                # Just for Posts and Replies (User deletes aren't announced)

                if to_delete:
                    if to_delete.deleted:
                        log_incoming_ap(id, APLOG_DELETE, APLOG_IGNORED, request_json if store_ap_json else None, 'Activity about local content which is already deleted')
                    else:
                        delete_post_or_comment(user, to_delete, store_ap_json, request_json)
                else:
                    log_incoming_ap(id, APLOG_DELETE, APLOG_FAILURE, request_json if store_ap_json else None, 'Delete: cannot find ' + ap_id)
                return

            if request_json['object']['type'] == 'Like' or request_json['object']['type'] == 'EmojiReact':  # Announced Upvote
                process_upvote(user, store_ap_json, request_json)
                return

            if request_json['object']['type'] == 'Dislike':                                                 # Announced Downvote
                if site.enable_downvotes is False:
                    log_incoming_ap(id, APLOG_DISLIKE, APLOG_IGNORED, request_json if store_ap_json else None, 'Dislike ignored because of allow_dislike setting')
                    return
                process_downvote(user, store_ap_json, request_json)
                return

            if request_json['object']['type'] == 'Flag':                                                            # Announce of reported content
                reported = find_reported_object(request_json['object']['object'])
                if reported:
                    process_report(user, reported, request_json['object'])
                    log_incoming_ap(id, APLOG_REPORT, APLOG_SUCCESS, request_json if store_ap_json else None)
                else:
                    log_incoming_ap(id, APLOG_REPORT, APLOG_IGNORED, request_json if store_ap_json else None, 'Report ignored due to missing content')
                return

            if request_json['object']['type'] == 'Lock':                                                            # Announce of post lock
                mod = user
                post_id = request_json['object']['object']
                post = Post.query.filter_by(ap_id=post_id).first()
                reason = request_json['object']['summary'] if 'summary' in request_json['object'] else ''
                if post:
                    if post.community.is_moderator(mod) or post.community.is_instance_admin(mod):
                        post.comments_enabled = False
                        db.session.commit()
                        add_to_modlog_activitypub('lock_post', mod, community_id=post.community.id,
                                                  link_text=shorten_string(post.title), link=f'post/{post.id}',
                                                  reason=reason)
                        log_incoming_ap(id, APLOG_LOCK, APLOG_SUCCESS, request_json if store_ap_json else None)
                    else:
                        log_incoming_ap(id, APLOG_LOCK, APLOG_FAILURE, request_json if store_ap_json else None, 'Lock: Does not have permission')
                else:
                    log_incoming_ap(id, APLOG_LOCK, APLOG_FAILURE, request_json if store_ap_json else None, 'Lock: post not found')
                return

            if request_json['object']['type'] == 'Add':                                                             # Announce of adding mods or stickying a post
                target = request_json['object']['target']
                featured_url = community.ap_featured_url
                moderators_url = community.ap_moderators_url
                if target == featured_url:
                    post = Post.query.filter_by(ap_id=request_json['object']['object']).first()
                    if post:
                        post.sticky = True
                        db.session.commit()
                        log_incoming_ap(id, APLOG_ADD, APLOG_SUCCESS, request_json if store_ap_json else None)
                    else:
                        log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Cannot find: ' +  request_json['object']['object'])
                    return
                if target == moderators_url:
                    user = find_actor_or_create(request_json['object']['object'])
                    if user:
                        existing_membership = CommunityMember.query.filter_by(community_id=community.id, user_id=user.id).first()
                        if existing_membership:
                            existing_membership.is_moderator = True
                        else:
                            new_membership = CommunityMember(community_id=community.id, user_id=user.id, is_moderator=True)
                            db.session.add(new_membership)
                        db.session.commit()
                        log_incoming_ap(id, APLOG_ADD, APLOG_SUCCESS, request_json if store_ap_json else None)
                    else:
                        log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Cannot find: ' + request_json['object']['object'])
                    return
                log_incoming_ap(id, APLOG_ADD, APLOG_FAILURE, request_json if store_ap_json else None, 'Unknown target for Add')
                return

            if request_json['object']['type'] == 'Remove':                                                          # Announce of removing mods or unstickying a post
                target = request_json['object']['target']
                featured_url = community.ap_featured_url
                moderators_url = community.ap_moderators_url
                if target == featured_url:
                    post = Post.query.filter_by(ap_id=request_json['object']['object']).first()
                    if post:
                        post.sticky = False
                        db.session.commit()
                        log_incoming_ap(id, APLOG_REMOVE, APLOG_SUCCESS, request_json if store_ap_json else None)
                    else:
                        log_incoming_ap(id, APLOG_REMOVE, APLOG_FAILURE, request_json if store_ap_json else None, 'Cannot find: ' + target)
                    return
                if target == moderators_url:
                    user = find_actor_or_create(request_json['object']['object'], create_if_not_found=False)
                    if user:
                        existing_membership = CommunityMember.query.filter_by(community_id=community.id, user_id=user.id).first()
                        if existing_membership:
                            existing_membership.is_moderator = False
                            db.session.commit()
                            log_incoming_ap(id, APLOG_REMOVE, APLOG_SUCCESS, request_json if store_ap_json else None)
                    else:
                        log_incoming_ap(id, APLOG_REMOVE, APLOG_FAILURE, request_json if store_ap_json else None, 'Cannot find: ' + request_json['object']['object'])
                    return
                log_incoming_ap(id, APLOG_REMOVE, APLOG_FAILURE, request_json if store_ap_json else None, 'Unknown target for Remove')
                return

            if request_json['object']['type'] == 'Block':                               # Announce of user ban. Mod is banning a user from a community,
                blocker = user                                                          # or an admin is banning a user from all the site's communities as part of a site ban
                blocked_ap_id = request_json['object']['object'].lower()
                blocked = User.query.filter_by(ap_profile_id=blocked_ap_id).first()
                if not blocked:
                    log_incoming_ap(id, APLOG_USERBAN, APLOG_IGNORED, request_json if store_ap_json else None, 'Does not exist here')
                    return
                remove_data = request_json['object']['removeData'] if 'removeData' in request_json['object'] else False

                if not community.is_moderator(blocker) and not community.is_instance_admin(blocker):
                    log_incoming_ap(id, APLOG_USERBAN, APLOG_FAILURE, request_json if store_ap_json else None, 'Does not have permission')
                    return

                if remove_data == True:
                    community_ban_remove_data(blocker.id, community.id, blocked)
                    log_incoming_ap(id, APLOG_USERBAN, APLOG_SUCCESS, request_json if store_ap_json else None)
                else:
                    log_incoming_ap(id, APLOG_USERBAN, APLOG_IGNORED, request_json if store_ap_json else None, 'Banned, but content retained')

                ban_user(blocker, blocked, community, request_json)
                return

            if request_json['object']['type'] == 'Undo':
                if request_json['object']['object']['type'] == 'Delete':                                                                    # Announce of undo of Delete
                    if isinstance(request_json['object']['object']['object'], str):
                        ap_id = request_json['object']['object']['object']  # lemmy
                    else:
                        ap_id = request_json['object']['object']['object']['id']  # kbin

                    restorer = user
                    to_restore = find_liked_object(ap_id)                           # a user or a mod/admin is undoing the delete of a post or reply
                    if to_restore:
                        if not to_restore.deleted:
                            log_incoming_ap(id, APLOG_UNDO_DELETE, APLOG_IGNORED, request_json if store_ap_json else None, 'Content was not deleted')
                        else:
                            restore_post_or_comment(restorer, to_restore, store_ap_json, request_json)
                    else:
                        log_incoming_ap(id, APLOG_UNDO_DELETE, APLOG_FAILURE, request_json if store_ap_json else None, 'Undo delete: cannot find ' + ap_id)
                    return

                if request_json['object']['object']['type'] == 'Like' or request_json['object']['object']['type'] == 'Dislike':             # Announce of undo of upvote or downvote
                    post = comment = None
                    target_ap_id = request_json['object']['object']['object']
                    post_or_comment = undo_vote(comment, post, target_ap_id, user)
                    if post_or_comment:
                        log_incoming_ap(id, APLOG_UNDO_VOTE, APLOG_SUCCESS, request_json if store_ap_json else None)
                    else:
                        log_incoming_ap(id, APLOG_UNDO_VOTE, APLOG_FAILURE, request_json if store_ap_json else None, 'Unfound object ' + target_ap_id)
                    return

                if request_json['object']['object']['type'] == 'Lock':                                                                      # Announce of undo of post lock
                    mod = user
                    post_id = request_json['object']['object']['object']
                    post = Post.query.filter_by(ap_id=post_id).first()
                    reason = request_json['object']['summary'] if 'summary' in request_json['object'] else ''
                    if post:
                        if post.community.is_moderator(mod) or post.community.is_instance_admin(mod):
                            post.comments_enabled = True
                            db.session.commit()
                            add_to_modlog_activitypub('unlock_post', mod, community_id=post.community.id,
                                                      link_text=shorten_string(post.title), link=f'post/{post.id}',
                                                      reason=reason)
                            log_incoming_ap(id, APLOG_LOCK, APLOG_SUCCESS, request_json if store_ap_json else None)
                        else:
                            log_incoming_ap(id, APLOG_LOCK, APLOG_FAILURE, request_json if store_ap_json else None, 'Lock: Does not have permission')
                    else:
                        log_incoming_ap(id, APLOG_LOCK, APLOG_FAILURE, request_json if store_ap_json else None, 'Lock: post not found')
                    return

                if request_json['object']['object']['type'] == 'Block':                         # Announce of undo of user ban. Mod is unbanning a user from a community,
                    blocker = user                                                              # or an admin is unbanning a user from all the site's communities as part of a site unban
                    blocked_ap_id = request_json['object']['object']['object'].lower()
                    blocked = User.query.filter_by(ap_profile_id=blocked_ap_id).first()
                    if not blocked:
                        log_incoming_ap(id, APLOG_USERBAN, APLOG_IGNORED, request_json if store_ap_json else None, 'Does not exist here')
                        return

                    if not community.is_moderator(blocker) and not community.is_instance_admin(blocker):
                        log_incoming_ap(id, APLOG_USERBAN, APLOG_FAILURE, request_json if store_ap_json else None, 'Does not have permission')
                        return

                    unban_user(blocker, blocked, community, request_json)
                    log_incoming_ap(id, APLOG_USERBAN, APLOG_SUCCESS, request_json if store_ap_json else None)

                    return

        log_incoming_ap(id, APLOG_MONITOR, APLOG_PROCESSING, request_json, 'Unmatched activity')


@celery.task
def process_delete_request(request_json, store_ap_json):
    with current_app.app_context():
        # this function processes self-deletes (retain case here, as user_removed_from_remote_server() uses a JSON request)
        id = request_json['id']
        user_ap_id = request_json['actor']
        user = User.query.filter_by(ap_profile_id=user_ap_id.lower()).first()
        if user:
            # check that the user really has been deleted, to avoid spoofing attacks
            if user_removed_from_remote_server(user_ap_id, is_piefed=user.instance.software == 'PieFed'):
                # soft self-delete
                user.deleted = True
                user.deleted_by = user.id
                db.session.commit()
                log_incoming_ap(id, APLOG_DELETE, APLOG_SUCCESS, request_json if store_ap_json else None)
            else:
                log_incoming_ap(id, APLOG_DELETE, APLOG_FAILURE, request_json if store_ap_json else None, 'User not actually deleted.')
        # TODO: acknowledge 'removeData' field from Lemmy
        # TODO: hard-delete in 7 days (should purge avatar and cover images, but keep posts and replies unless already soft-deleted by removeData = True)


def announce_activity_to_followers(community, creator, activity):
    # avoid announcing activity sent to local users unless it is also in a local community
    if not community.is_local():
        return

    # remove context from what will be inner object
    del activity["@context"]

    announce_activity = {
        '@context': default_context(),
        "actor": community.public_url(),
        "to": [
            "https://www.w3.org/ns/activitystreams#Public"
        ],
        "object": activity,
        "cc": [
            f"{community.public_url()}/followers"
        ],
        "type": "Announce",
        "id": f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
    }

    for instance in community.following_instances(include_dormant=True):
        # awaken dormant instances if they've been sleeping for long enough to be worth trying again
        awaken_dormant_instance(instance)

        # All good? Send!
        if instance and instance.online() and not instance_blocked(instance.inbox):
            if creator.instance_id != instance.id:    # don't send it to the instance that hosts the creator as presumably they already have the content
                send_to_remote_instance(instance.id, community.id, announce_activity)


@bp.route('/c/<actor>/outbox', methods=['GET'])
def community_outbox(actor):
    actor = actor.strip()
    community = Community.query.filter_by(name=actor, banned=False, ap_id=None).first()
    if community is not None:
        sticky_posts = community.posts.filter(Post.sticky == True, Post.deleted == False).order_by(desc(Post.posted_at)).limit(50).all()
        remaining_limit = 50 - len(sticky_posts)
        remaining_posts = community.posts.filter(Post.sticky == False, Post.deleted == False).order_by(desc(Post.posted_at)).limit(remaining_limit).all()
        posts = sticky_posts + remaining_posts

        community_data = {
            "@context": default_context(),
            "type": "OrderedCollection",
            "id": f"https://{current_app.config['SERVER_NAME']}/c/{actor}/outbox",
            "totalItems": len(posts),
            "orderedItems": []
        }

        for post in posts:
            community_data['orderedItems'].append(post_to_activity(post, community))

        return jsonify(community_data)


@bp.route('/c/<actor>/featured', methods=['GET'])
def community_featured(actor):
    actor = actor.strip()
    community = Community.query.filter_by(name=actor, banned=False, ap_id=None).first()
    if community is not None:
        posts = Post.query.filter_by(community_id=community.id, sticky=True, deleted=False).all()

        community_data = {
            "@context": default_context(),
            "type": "OrderedCollection",
            "id": f"https://{current_app.config['SERVER_NAME']}/c/{actor}/featured",
            "totalItems": len(posts),
            "orderedItems": []
        }

        for post in posts:
            community_data['orderedItems'].append(post_to_page(post))

        return jsonify(community_data)


@bp.route('/c/<actor>/moderators', methods=['GET'])
def community_moderators_route(actor):
    actor = actor.strip()
    community = Community.query.filter_by(name=actor, banned=False, ap_id=None).first()
    if community is not None:
        moderator_ids = community_moderators(community.id)
        moderators = User.query.filter(User.id.in_([mod.user_id for mod in moderator_ids])).all()
        community_data = {
            "@context": default_context(),
            "type": "OrderedCollection",
            "id": f"https://{current_app.config['SERVER_NAME']}/c/{actor}/moderators",
            "totalItems": len(moderators),
            "orderedItems": []
        }

        for moderator in moderators:
            community_data['orderedItems'].append(moderator.ap_profile_id)

        return jsonify(community_data)


@celery.task
def process_user_follow_request(request_json, activitypublog_id, remote_user_id):
    activity_log = ActivityPubLog.query.get(activitypublog_id)
    local_user_ap_id = request_json['object']
    follow_id = request_json['id']
    local_user = find_actor_or_create(local_user_ap_id, create_if_not_found=False)
    remote_user = User.query.get(remote_user_id)
    if local_user and local_user.is_local() and not remote_user.is_local():
        existing_follower = UserFollower.query.filter_by(local_user_id=local_user.id, remote_user_id=remote_user.id).first()
        if not existing_follower:
            auto_accept = not local_user.ap_manually_approves_followers
            new_follower = UserFollower(local_user_id=local_user.id, remote_user_id=remote_user.id, is_accepted=auto_accept)
            if not local_user.ap_followers_url:
                local_user.ap_followers_url = local_user.public_url() + '/followers'
            db.session.add(new_follower)
        accept = {
            "@context": default_context(),
            "actor": local_user.public_url(),
            "to": [
                remote_user.public_url()
            ],
            "object": {
                "actor": remote_user.public_url(),
                "to": None,
                "object": local_user.public_url(),
                "type": "Follow",
                "id": follow_id
            },
            "type": "Accept",
            "id": f"https://{current_app.config['SERVER_NAME']}/activities/accept/" + gibberish(32)
        }
        if post_request(remote_user.ap_inbox_url, accept, local_user.private_key, f"{local_user.public_url()}#main-key") is True:
            activity_log.result = 'success'
        else:
            activity_log.exception_message = 'Error sending Accept'
    else:
        activity_log.exception_message = 'Could not find local user'
        activity_log.result = 'failure'

    db.session.commit()


@bp.route('/c/<actor>/followers', methods=['GET'])
def community_followers(actor):
    actor = actor.strip()
    community = Community.query.filter_by(name=actor, banned=False, ap_id=None).first()
    if community is not None:
        result = {
            "@context": default_context(),
            "id": f'https://{current_app.config["SERVER_NAME"]}/c/{actor}/followers',
            "type": "Collection",
            "totalItems": community_members(community.id),
            "items": []
        }
        resp = jsonify(result)
        resp.content_type = 'application/activity+json'
        return resp
    else:
        abort(404)


@bp.route('/u/<actor>/followers', methods=['GET'])
def user_followers(actor):
    actor = actor.strip()
    user = User.query.filter_by(user_name=actor, banned=False, ap_id=None).first()
    if user is not None and user.ap_followers_url:
        # Get all followers, except those that are blocked by user by doing an outer join
        followers = User.query.join(UserFollower, User.id == UserFollower.remote_user_id)\
            .outerjoin(UserBlock, (User.id == UserBlock.blocker_id) & (UserFollower.local_user_id == UserBlock.blocked_id))\
            .filter((UserFollower.local_user_id == user.id) & (UserBlock.id == None))\
            .all()

        items = []
        for f in followers:
            items.append(f.ap_public_url)
        result = {
            "@context": default_context(),
            "id": user.ap_followers_url,
            "type": "Collection",
            "totalItems": len(items),
            "items": items
        }
        resp = jsonify(result)
        resp.content_type = 'application/activity+json'
        return resp
    else:
        abort(404)


@bp.route('/comment/<int:comment_id>', methods=['GET', 'HEAD'])
def comment_ap(comment_id):
    reply = PostReply.query.get_or_404(comment_id)
    if is_activitypub_request():
        reply_data = comment_model_to_json(reply) if request.method == 'GET' else []
        resp = jsonify(reply_data)
        resp.content_type = 'application/activity+json'
        resp.headers.set('Vary', 'Accept')
        resp.headers.set('Link', f'<https://{current_app.config["SERVER_NAME"]}/comment/{reply.id}>; rel="alternate"; type="text/html"')
        return resp
    else:
        return continue_discussion(reply.post.id, comment_id)


@bp.route('/post/<int:post_id>/', methods=['GET', 'HEAD'])
def post_ap2(post_id):
    return redirect(url_for('activitypub.post_ap', post_id=post_id))


@bp.route('/post/<int:post_id>', methods=['GET', 'HEAD', 'POST'])
def post_ap(post_id):
    if (request.method == 'GET' or request.method == 'HEAD') and is_activitypub_request():
        post = Post.query.get_or_404(post_id)
        if request.method == 'GET':
            post_data = post_to_page(post)
            post_data['@context'] = default_context()
        else:  # HEAD request
            post_data = []
        resp = jsonify(post_data)
        resp.content_type = 'application/activity+json'
        resp.headers.set('Vary', 'Accept')
        resp.headers.set('Link', f'<https://{current_app.config["SERVER_NAME"]}/post/{post.id}>; rel="alternate"; type="text/html"')
        return resp
    else:
        return show_post(post_id)


@bp.route('/activities/<type>/<id>')
@cache.cached(timeout=600)
def activities_json(type, id):
    activity = ActivityPubLog.query.filter_by(activity_id=f"https://{current_app.config['SERVER_NAME']}/activities/{type}/{id}").first()
    if activity:
        if activity.activity_json is not None:
            activity_json = json.loads(activity.activity_json)
        else:
            activity_json = {}
        resp = jsonify(activity_json)
        resp.content_type = 'application/activity+json'
        return resp
    else:
        abort(404)


# Other instances can query the result of their POST to the inbox by using this endpoint. The ID of the activity they
# sent (minus the https:// on the front) is the id parameter. e.g. https://piefed.ngrok.app/activity_result/piefed.ngrok.app/activities/announce/EfjyZ3BE5SzQK0C
@bp.route('/activity_result/<path:id>')
def activity_result(id):
    activity = ActivityPubLog.query.filter_by(activity_id=f'https://{id}').first()
    if activity:
        if activity.result == 'success':
            return jsonify('Ok')
        else:
            return jsonify({'error': activity.result, 'message': activity.exception_message})
    else:
        abort(404)


def process_new_content(user, community, store_ap_json, request_json, announced=True):
    id = request_json['id']
    if not announced:
        in_reply_to = request_json['object']['inReplyTo'] if 'inReplyTo' in request_json['object'] else None
        ap_id = request_json['object']['id']
        announce_id = None
        activity_json = request_json
    else:
        in_reply_to = request_json['object']['object']['inReplyTo'] if 'inReplyTo' in request_json['object']['object'] else None
        ap_id = request_json['object']['object']['id']
        announce_id = request_json['id']
        activity_json = request_json['object']

    if not in_reply_to: # Creating a new post
        post = Post.query.filter_by(ap_id=ap_id).first()
        if post:
            if activity_json['type'] == 'Create':
                log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Create processed after Update')
                return
            if user.id == post.user_id:
                update_post_from_activity(post, activity_json)
                log_incoming_ap(id, APLOG_UPDATE, APLOG_SUCCESS, request_json if store_ap_json else None)
                if not announced:
                    announce_activity_to_followers(post.community, post.author, request_json)
                return
            else:
                log_incoming_ap(id, APLOG_UPDATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Edit attempt denied')
                return
        else:
            if can_create_post(user, community):
                try:
                    post = create_post(store_ap_json, community, activity_json, user, announce_id=announce_id)
                    if post:
                        log_incoming_ap(id, APLOG_CREATE, APLOG_SUCCESS, request_json if store_ap_json else None)
                        if not announced:
                            announce_activity_to_followers(community, user, request_json)
                        return
                except TypeError as e:
                    current_app.logger.error('TypeError: ' + str(request_json))
                    log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'TypeError. See log file.')
                    return
            else:
                log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'User cannot create post in Community')
                return
    else:   # Creating a reply / comment
        reply = PostReply.query.filter_by(ap_id=ap_id).first()
        if reply:
            if activity_json['type'] == 'Create':
                log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Create processed after Update')
                return
            if user.id == reply.user_id:
                update_post_reply_from_activity(reply, activity_json)
                log_incoming_ap(id, APLOG_UPDATE, APLOG_SUCCESS, request_json if store_ap_json else None)
                if not announced:
                    announce_activity_to_followers(reply.community, reply.author, request_json)
                return
            else:
                log_incoming_ap(id, APLOG_UPDATE, APLOG_FAILURE, request_json if store_ap_json else None, 'Edit attempt denied')
                return
        else:
            if can_create_post_reply(user, community):
                try:
                    reply = create_post_reply(store_ap_json, community, in_reply_to, activity_json, user, announce_id=announce_id)
                    if reply:
                        log_incoming_ap(id, APLOG_CREATE, APLOG_SUCCESS, request_json if store_ap_json else None)
                        if not announced:
                            announce_activity_to_followers(community, user, request_json)
                    return
                except TypeError as e:
                    current_app.logger.error('TypeError: ' + str(request_json))
                    log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'TypeError. See log file.')
                    return
            else:
                log_incoming_ap(id, APLOG_CREATE, APLOG_FAILURE, request_json if store_ap_json else None, 'User cannot create reply in Community')
                return


def process_upvote(user, store_ap_json, request_json, announced=True):
    id = request_json['id']
    ap_id = request_json['object'] if not announced else request_json['object']['object']
    if isinstance(ap_id, dict) and 'id' in ap_id:
        ap_id = ap_id['id']
    liked = find_liked_object(ap_id)
    if liked is None:
        log_incoming_ap(id, APLOG_LIKE, APLOG_FAILURE, request_json if store_ap_json else None, 'Unfound object ' + ap_id)
        return
    if can_upvote(user, liked.community):
        if isinstance(liked, (Post, PostReply)):
            liked.vote(user, 'upvote')
            log_incoming_ap(id, APLOG_LIKE, APLOG_SUCCESS, request_json if store_ap_json else None)
            if not announced:
                announce_activity_to_followers(liked.community, user, request_json)
    else:
        log_incoming_ap(id, APLOG_LIKE, APLOG_IGNORED, request_json if store_ap_json else None, 'Cannot upvote this')


def process_downvote(user, store_ap_json, request_json, announced=True):
    id = request_json['id']
    ap_id = request_json['object'] if not announced else request_json['object']['object']
    if isinstance(ap_id, dict) and 'id' in ap_id:
        ap_id = ap_id['id']
    liked = find_liked_object(ap_id)
    if liked is None:
        log_incoming_ap(id, APLOG_DISLIKE, APLOG_FAILURE, request_json if store_ap_json else None, 'Unfound object ' + ap_id)
        return
    if can_downvote(user, liked.community):
        if isinstance(liked, (Post, PostReply)):
            liked.vote(user, 'downvote')
            log_incoming_ap(id, APLOG_DISLIKE, APLOG_SUCCESS, request_json if store_ap_json else None)
            if not announced:
                announce_activity_to_followers(liked.community, user, request_json)
    else:
        log_incoming_ap(id, APLOG_DISLIKE, APLOG_IGNORED, request_json if store_ap_json else None, 'Cannot downvote this')
