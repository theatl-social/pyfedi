from urllib.parse import urlparse, parse_qs

from flask_login import current_user

from app import db, constants, cache, celery
from app.activitypub import bp
from flask import request, current_app, abort, jsonify, json, g, url_for, redirect, make_response

from app.activitypub.signature import HttpSignature, post_request, VerificationError, default_context
from app.community.routes import show_community
from app.community.util import send_to_remote_instance
from app.post.routes import continue_discussion, show_post
from app.user.routes import show_profile
from app.constants import POST_TYPE_LINK, POST_TYPE_IMAGE, SUBSCRIPTION_MEMBER
from app.models import User, Community, CommunityJoinRequest, CommunityMember, CommunityBan, ActivityPubLog, Post, \
    PostReply, Instance, PostVote, PostReplyVote, File, AllowedInstances, BannedInstances, utcnow, Site, Notification, \
    ChatMessage, Conversation, UserFollower, UserBlock, Poll, PollChoice
from app.activitypub.util import public_key, users_total, active_half_year, active_month, local_posts, local_comments, \
    post_to_activity, find_actor_or_create, instance_blocked, find_reply_parent, find_liked_object, \
    lemmy_site_data, instance_weight, is_activitypub_request, downvote_post_reply, downvote_post, upvote_post_reply, \
    upvote_post, delete_post_or_comment, community_members, \
    user_removed_from_remote_server, create_post, create_post_reply, update_post_reply_from_activity, \
    update_post_from_activity, undo_vote, undo_downvote, post_to_page, get_redis_connection, find_reported_object, \
    process_report, ensure_domains_match, can_edit, can_delete, remove_data_from_banned_user, resolve_remote_post, \
    inform_followers_of_post_update, comment_model_to_json, restore_post_or_comment
from app.utils import gibberish, get_setting, is_image_url, allowlist_html, render_template, \
    domain_from_url, markdown_to_html, community_membership, ap_datetime, ip_address, can_downvote, \
    can_upvote, can_create_post, awaken_dormant_instance, shorten_string, can_create_post_reply, sha256_digest, \
    community_moderators, lemmy_markdown_to_html, make_cache_key
from sqlalchemy import desc
import werkzeug.exceptions


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
        user = User.query.filter_by(user_name=actor.strip(), deleted=False, banned=False, ap_id=None).first()
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
                                "href": f"https://{current_app.config['SERVER_NAME']}/nodeinfo/2.0"}]}
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
                "openRegistrations": g.site.registration_mode == 'Open'
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
    for instance in instances:
        instance_data = {"id": instance.id, "domain": instance.domain, "published": instance.created_at.isoformat(), "updated": instance.updated_at.isoformat()}
        if instance.software:
            instance_data['software'] = instance.software
        if instance.version:
            instance_data['version'] = instance.version
        linked.append(instance_data)
    for instance in AllowedInstances.query.all():
        allowed.append({"id": instance.id, "domain": instance.domain, "published": utcnow(), "updated": utcnow()})
    for instance in BannedInstances.query.all():
        blocked.append({"id": instance.id, "domain": instance.domain, "published": utcnow(), "updated": utcnow()})
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
            user: User = User.query.filter_by(user_name=actor, ap_id=None).first()
            if user is None:
                user = User.query.filter_by(ap_profile_id=f'https://{current_app.config["SERVER_NAME"]}/u/{actor.lower()}', deleted=False, ap_id=None).first()
    else:
        if '@' in actor:
            user: User = User.query.filter_by(ap_id=actor.lower(), deleted=False, banned=False).first()
        else:
            user: User = User.query.filter_by(user_name=actor, deleted=False, ap_id=None).first()
            if user is None:
                user = User.query.filter_by(ap_profile_id=f'https://{current_app.config["SERVER_NAME"]}/u/{actor.lower()}', deleted=False, ap_id=None).first()

    if user is not None:
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
                            "id": user.public_url(),
                            "preferredUsername": actor,
                            "name": user.title if user.title else user.user_name,
                            "inbox": f"{user.public_url()}/inbox",
                            "outbox": f"{user.public_url()}/outbox",
                            "discoverable": user.searchable,
                            "indexable": user.indexable,
                            "manuallyApprovesFollowers": False if not user.ap_manually_approves_followers else user.ap_manually_approves_followers,
                            "publicKey": {
                                "id": f"{user.public_url()}#main-key",
                                "owner": user.public_url(),
                                "publicKeyPem": user.public_key      # .replace("\n", "\\n")    #LOOKSWRONG
                            },
                            "endpoints": {
                                "sharedInbox": f"https://{server}/inbox"
                            },
                            "published": ap_datetime(user.created),
                        }
            if user.avatar_id is not None:
                actor_data["icon"] = {
                    "type": "Image",
                    "url": f"https://{current_app.config['SERVER_NAME']}{user.avatar_image()}"
                }
            if user.cover_id is not None:
                actor_data["image"] = {
                    "type": "Image",
                    "url": f"https://{current_app.config['SERVER_NAME']}{user.cover_image()}"
                }
            if user.about_html:
                actor_data['summary'] = user.about_html
            if user.matrix_user_id:
                actor_data['matrixUserId'] = user.matrix_user_id
            resp = jsonify(actor_data)
            resp.content_type = 'application/activity+json'
            return resp
        else:
            return show_profile(user)
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
            return resp
        else:   # browser request - return html
            return show_community(community)
    else:
        abort(404)


@bp.route('/inbox', methods=['GET', 'POST'])
def shared_inbox():
    if request.method == 'POST':
        # save all incoming data to aid in debugging and development. Set result to 'success' if things go well
        activity_log = ActivityPubLog(direction='in', result='failure')

        try:
            request_json = request.get_json(force=True)
        except werkzeug.exceptions.BadRequest as e:
            activity_log.exception_message = 'Unable to parse json body: ' + e.description
            activity_log.result = 'failure'
            db.session.add(activity_log)
            db.session.commit()
            return ''

        if 'id' in request_json:
            redis_client = get_redis_connection()
            if redis_client.get(request_json['id']) is not None:   # Lemmy has an extremely short POST timeout and tends to retry unnecessarily. Ignore their retries.
                activity_log.result = 'ignored'
                activity_log.exception_message = 'Unnecessary retry attempt'
                db.session.add(activity_log)
                db.session.commit()
                return ''

            redis_client.set(request_json['id'], 1, ex=90)  # Save the activity ID into redis, to avoid duplicate activities that Lemmy sometimes sends
            activity_log.activity_id = request_json['id']
            g.site = Site.query.get(1)                      # g.site is not initialized by @app.before_request when request.path == '/inbox'
            if g.site.log_activitypub_json:
                activity_log.activity_json = json.dumps(request_json)
            activity_log.result = 'processing'
            db.session.add(activity_log)
            db.session.commit()

            # When a user is deleted, the only way to be fairly sure they get deleted everywhere is to tell the whole fediverse.
            if 'type' in request_json and request_json['type'] == 'Delete' and request_json['id'].endswith('#delete'):
                if current_app.debug:
                    process_delete_request(request_json, activity_log.id, ip_address())
                else:
                    process_delete_request.delay(request_json, activity_log.id, ip_address())
                return ''
            # Ignore unutilised PeerTube activity
            if 'actor' in request_json and request_json['actor'].endswith('accounts/peertube'):
                activity_log.result = 'ignored'
                activity_log.exception_message = 'PeerTube View or CacheFile activity'
                db.session.add(activity_log)
                db.session.commit()
                return ''

        else:
            activity_log.activity_id = ''
            if g.site.log_activitypub_json:
                activity_log.activity_json = json.dumps(request_json)
            db.session.add(activity_log)
            db.session.commit()

        actor = find_actor_or_create(request_json['actor']) if 'actor' in request_json else None
        if actor is not None:
            try:
                HttpSignature.verify_request(request, actor.public_key, skip_date=True)
                if current_app.debug:
                    process_inbox_request(request_json, activity_log.id, ip_address())
                else:
                    process_inbox_request.delay(request_json, activity_log.id, ip_address())
                return ''
            except VerificationError as e:
                activity_log.exception_message = 'Could not verify signature: ' + str(e)
                activity_log.result = 'failure'
                db.session.commit()
                return '', 400
        else:
            actor_name = request_json['actor'] if 'actor' in request_json else ''
            activity_log.exception_message = f'Actor could not be found: {actor_name}'

        if activity_log.exception_message is not None:
            activity_log.result = 'failure'
        db.session.commit()
    return ''


@bp.route('/site_inbox', methods=['GET', 'POST'])
def site_inbox():
    return shared_inbox()


@celery.task
def process_inbox_request(request_json, activitypublog_id, ip_address):
    with current_app.app_context():
        activity_log = ActivityPubLog.query.get(activitypublog_id)
        site = Site.query.get(1)    # can't use g.site because celery doesn't use Flask's g variable
        if 'type' in request_json:
            activity_log.activity_type = request_json['type']
            if not instance_blocked(request_json['id']):
                # Create is new content. Update is often an edit, but Updates from Lemmy can also be new content
                if request_json['type'] == 'Create' or request_json['type'] == 'Update':
                    activity_log.activity_type = 'Create'
                    user_ap_id = request_json['object']['attributedTo'] if 'attributedTo' in request_json['object'] and isinstance(request_json['object']['attributedTo'], str) else None
                    if user_ap_id is None:  # if there is no attributedTo, fall back to the actor on the parent object
                        user_ap_id = request_json['actor'] if 'actor' in request_json and isinstance(request_json['actor'], str) else None
                    if request_json['object']['type'] == 'ChatMessage':
                        activity_log.activity_type = 'Create ChatMessage'
                        sender = find_actor_or_create(user_ap_id)
                        recipient_ap_id = request_json['object']['to'][0]
                        recipient = find_actor_or_create(recipient_ap_id)
                        if sender and recipient and recipient.is_local():
                            if sender.created_recently() or sender.reputation <= -10:
                                activity_log.exception_message = "Sender not eligible to send"
                            elif recipient.has_blocked_user(sender.id) or recipient.has_blocked_instance(sender.instance_id):
                                activity_log.exception_message = "Sender blocked by recipient"
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
                                                          body=request_json['object']['source']['content'],
                                                          body_html=lemmy_markdown_to_html(request_json['object']['source']['content']),
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
                                activity_log.result = 'success'
                    else:
                        try:
                            community_ap_id = ''
                            locations = ['audience', 'cc', 'to']
                            if 'object' in request_json:
                                rjs = [request_json, request_json['object']]
                            else:
                                rjs = [request_json]
                            followers_suffix = '/followers'
                            for rj in rjs:
                                for location in locations:
                                    if location in rj:
                                        potential_id = rj[location]
                                        if isinstance(potential_id, str):
                                            if not potential_id.startswith('https://www.w3.org') and not potential_id.endswith(followers_suffix):
                                                community_ap_id = potential_id
                                        if isinstance(potential_id, list):
                                            for c in potential_id:
                                                if not c.startswith('https://www.w3.org') and not c.endswith(followers_suffix):
                                                    community_ap_id = c
                                                    break
                                    if community_ap_id:
                                        break
                                if community_ap_id:
                                    break
                            if not community_ap_id and 'object' in request_json and 'inReplyTo' in request_json['object']:
                                post_being_replied_to = Post.query.filter_by(ap_id=request_json['object']['inReplyTo']).first()
                                if post_being_replied_to:
                                    community_ap_id = post_being_replied_to.community.ap_profile_id
                                else:
                                    comment_being_replied_to = PostReply.query.filter_by(ap_id=request_json['object']['inReplyTo']).first()
                                    if comment_being_replied_to:
                                        community_ap_id = comment_being_replied_to.community.ap_profile_id
                            if not community_ap_id and 'object' in request_json and request_json['object']['type'] == 'Video': # PeerTube
                                if 'attributedTo' in request_json['object'] and isinstance(request_json['object']['attributedTo'], list):
                                    for a in request_json['object']['attributedTo']:
                                        if a['type'] == 'Group':
                                            community_ap_id = a['id']
                                        if a['type'] == 'Person':
                                            user_ap_id = a['id']
                            if not community_ap_id:
                                activity_log.result = 'failure'
                                activity_log.exception_message = 'Unable to extract community'
                                db.session.commit()
                                return
                        except:
                            activity_log.activity_type = 'exception'
                            db.session.commit()
                            return
                        if 'object' in request_json:
                            if not ensure_domains_match(request_json['object']):
                                activity_log.result = 'failure'
                                activity_log.exception_message = 'Domains do not match'
                                db.session.commit()
                                return
                        community = find_actor_or_create(community_ap_id, community_only=True)
                        if community and community.local_only:
                            activity_log.exception_message = 'Remote Create in local_only community'
                            activity_log.result = 'ignored'
                            db.session.commit()
                            return
                        user = find_actor_or_create(user_ap_id)
                        if (user and not user.is_local()) and community:
                            user.last_seen = community.last_active = site.last_active = utcnow()

                            object_type = request_json['object']['type']
                            new_content_types = ['Page', 'Article', 'Link', 'Note', 'Question']
                            if object_type in new_content_types:  # create or update a post
                                in_reply_to = request_json['object']['inReplyTo'] if 'inReplyTo' in request_json['object'] else None
                                if not in_reply_to:
                                    post = Post.query.filter_by(ap_id=request_json['object']['id']).first()
                                    if post:
                                        if request_json['type'] == 'Create':
                                            activity_log.result = 'ignored'
                                            activity_log.exception_message = 'Create received for already known object'
                                            db.session.commit()
                                            return
                                        else:
                                            activity_log.activity_type = 'Update'
                                            if can_edit(request_json['actor'], post):
                                                update_post_from_activity(post, request_json)
                                                announce_activity_to_followers(post.community, post.author, request_json)
                                                activity_log.result = 'success'
                                            else:
                                                activity_log.exception_message = 'Edit attempt denied'
                                    else:
                                        if can_create_post(user, community):
                                            try:
                                                post = create_post(activity_log, community, request_json, user)
                                                if post:
                                                    announce_activity_to_followers(community, user, request_json)
                                            except TypeError as e:
                                                activity_log.exception_message = 'TypeError. See log file.'
                                                current_app.logger.error('TypeError: ' + str(request_json))
                                                post = None
                                        else:
                                            post = None
                                else:
                                    reply = PostReply.query.filter_by(ap_id=request_json['object']['id']).first()
                                    if reply:
                                        if request_json['type'] == 'Create':
                                            activity_log.result = 'ignored'
                                            activity_log.exception_message = 'Create received for already known object'
                                            db.session.commit()
                                            return
                                        else:
                                            activity_log.activity_type = 'Update'
                                            if can_edit(request_json['actor'], reply):
                                                update_post_reply_from_activity(reply, request_json)
                                                announce_activity_to_followers(reply.community, reply.author, request_json)
                                                activity_log.result = 'success'
                                            else:
                                                activity_log.exception_message = 'Edit attempt denied'
                                    else:
                                        if can_create_post_reply(user, community):
                                            try:
                                                post_reply = create_post_reply(activity_log, community, in_reply_to, request_json, user)
                                                if post_reply:
                                                    announce_activity_to_followers(community, user, request_json)
                                            except TypeError as e:
                                                activity_log.exception_message = 'TypeError. See log file.'
                                                current_app.logger.error('TypeError: ' + str(request_json))
                                                post = None
                                        else:
                                            post = None
                            elif object_type == 'Video':  # PeerTube: editing a video (PT doesn't seem to Announce these)
                                post = Post.query.filter_by(ap_id=request_json['object']['id']).first()
                                activity_log.activity_type = 'Update'
                                if post:
                                    if can_edit(request_json['actor'], post):
                                        update_post_from_activity(post, request_json)
                                        activity_log.result = 'success'
                                    else:
                                        activity_log.exception_message = 'Edit attempt denied'
                                else:
                                    activity_log.exception_message = 'Post not found'
                            else:
                                activity_log.exception_message = 'Unacceptable type (create): ' + object_type
                        else:
                            if user is None or community is None:
                                activity_log.exception_message = 'Blocked or unfound user or community'
                            if user and user.is_local():
                                activity_log.exception_message = 'Activity about local content which is already present'
                                activity_log.result = 'ignored'

                # Announce is new content and votes that happened on a remote server.
                if request_json['type'] == 'Announce':
                    if isinstance(request_json['object'], str):  # Mastodon, PeerTube, A.gup.pe
                        activity_log.activity_json = json.dumps(request_json)
                        activity_log.exception_message = 'invalid json?'
                        if 'actor' in request_json:
                            community = find_actor_or_create(request_json['actor'], community_only=True, create_if_not_found=False)
                            if community:
                                post = resolve_remote_post(request_json['object'], community.id, request_json['actor'])
                    elif request_json['object']['type'] == 'Create' or request_json['object']['type'] == 'Update':
                        activity_log.activity_type = request_json['object']['type']
                        if 'object' in request_json and 'object' in request_json['object']:
                            if not ensure_domains_match(request_json['object']['object']):
                                activity_log.exception_message = 'Domains do not match'
                                activity_log.result = 'failure'
                                db.session.commit()
                                return
                        user_ap_id = request_json['object']['object']['attributedTo']
                        try:
                            community_ap_id = request_json['object']['audience'] if 'audience' in request_json['object'] else request_json['actor']
                        except KeyError:
                            activity_log.activity_type = 'exception'
                            db.session.commit()
                            return
                        community = find_actor_or_create(community_ap_id, community_only=True)
                        user = find_actor_or_create(user_ap_id)
                        if (user and not user.is_local()) and community:
                            user.last_seen = community.last_active = site.last_active = utcnow()
                            object_type = request_json['object']['object']['type']
                            new_content_types = ['Page', 'Article', 'Link', 'Note']
                            if object_type in new_content_types:  # create a new post
                                in_reply_to = request_json['object']['object']['inReplyTo'] if 'inReplyTo' in \
                                                                                               request_json['object']['object'] else None
                                if not in_reply_to:
                                    post = Post.query.filter_by(ap_id=request_json['object']['object']['id']).first()
                                    if post:
                                        if request_json['object']['type'] == 'Create':
                                            activity_log.result = 'ignored'
                                            activity_log.exception_message = 'Create received for already known object'
                                            db.session.commit()
                                            return
                                        else:
                                            try:
                                                update_post_from_activity(post, request_json['object'])
                                            except KeyError:
                                                activity_log.result = 'exception'
                                                db.session.commit()
                                                return
                                            activity_log.result = 'success'
                                    else: # activity was a Create, or an Update sent instead of a Create
                                        if can_create_post(user, community):
                                            post = create_post(activity_log, community, request_json['object'], user, announce_id=request_json['id'])
                                        else:
                                            post = None
                                else:
                                    reply = PostReply.query.filter_by(ap_id=request_json['object']['object']['id']).first()
                                    if reply:
                                        if request_json['object']['type'] == 'Create':
                                            activity_log.result = 'ignored'
                                            activity_log.exception_message = 'Create received for already known object'
                                            db.session.commit()
                                            return
                                        else:
                                            try:
                                                update_post_reply_from_activity(reply, request_json['object'])
                                            except KeyError:
                                                activity_log.result = 'exception'
                                                db.session.commit()
                                                return
                                            activity_log.result = 'success'
                                    else: # activity was a Create, or an Update sent instead of a Create
                                        if can_create_post_reply(user, community):
                                            post = create_post_reply(activity_log, community, in_reply_to, request_json['object'], user, announce_id=request_json['id'])
                                        else:
                                            post = None
                            else:
                                activity_log.exception_message = 'Unacceptable type: ' + object_type
                        else:
                            if user is None or community is None:
                                activity_log.exception_message = 'Blocked or unfound user or community'
                            if user and user.is_local():
                                activity_log.exception_message = 'Activity about local content which is already present'
                                activity_log.result = 'ignored'

                    elif request_json['object']['type'] == 'Like' or request_json['object']['type'] == 'EmojiReact':
                        activity_log.activity_type = request_json['object']['type']
                        user_ap_id = request_json['object']['actor']
                        liked_ap_id = request_json['object']['object']
                        user = find_actor_or_create(user_ap_id)
                        liked = find_liked_object(liked_ap_id)

                        if user is None:
                            activity_log.exception_message = 'Blocked or unfound user'
                        elif liked is None:
                            activity_log.exception_message = 'Unfound object ' + liked_ap_id
                        elif user.is_local():
                            activity_log.exception_message = 'Activity about local content which is already present'
                            activity_log.result = 'ignored'
                        elif can_upvote(user, liked.community):
                            # insert into voted table
                            if liked is None:
                                activity_log.exception_message = 'Liked object not found'
                            elif liked is not None and isinstance(liked, Post):
                                upvote_post(liked, user)
                                activity_log.result = 'success'
                            elif liked is not None and isinstance(liked, PostReply):
                                upvote_post_reply(liked, user)
                                activity_log.result = 'success'
                            else:
                                activity_log.exception_message = 'Could not detect type of like'
                        else:
                            activity_log.exception_message = 'Cannot upvote this'
                            activity_log.result = 'ignored'

                    elif request_json['object']['type'] == 'Dislike':
                        activity_log.activity_type = request_json['object']['type']
                        if site.enable_downvotes is False:
                            activity_log.exception_message = 'Dislike ignored because of allow_dislike setting'
                        else:
                            user_ap_id = request_json['object']['actor']
                            liked_ap_id = request_json['object']['object']
                            user = find_actor_or_create(user_ap_id)
                            disliked = find_liked_object(liked_ap_id)
                            if user is None:
                                activity_log.exception_message = 'Blocked or unfound user'
                            elif disliked is None:
                                activity_log.exception_message = 'Unfound object ' + liked_ap_id
                            elif user.is_local():
                                activity_log.exception_message = 'Activity about local content which is already present'
                                activity_log.result = 'ignored'
                            elif can_downvote(user, disliked.community, site):
                                # insert into voted table
                                if disliked is None:
                                    activity_log.exception_message = 'Liked object not found'
                                elif isinstance(disliked, (Post, PostReply)):
                                    if isinstance(disliked, Post):
                                        downvote_post(disliked, user)
                                    elif isinstance(disliked, PostReply):
                                        downvote_post_reply(disliked, user)
                                    activity_log.result = 'success'
                                    # todo: recalculate 'hotness' of liked post/reply
                                else:
                                    activity_log.exception_message = 'Could not detect type of like'
                            else:
                                activity_log.exception_message = 'Cannot downvote this'
                                activity_log.result = 'ignored'
                    elif request_json['object']['type'] == 'Delete':
                        activity_log.activity_type = request_json['object']['type']
                        user_ap_id = request_json['object']['actor']
                        community_ap_id = request_json['object']['audience'] if 'audience' in request_json['object'] else request_json['actor']
                        to_be_deleted_ap_id = request_json['object']['object']
                        if isinstance(to_be_deleted_ap_id, dict):
                            activity_log.result = 'failure'
                            activity_log.exception_message = 'dict instead of string ' + str(to_be_deleted_ap_id)
                        else:
                            post = Post.query.filter_by(ap_id=to_be_deleted_ap_id).first()
                            if post and post.url and post.cross_posts is not None:
                                old_cross_posts = Post.query.filter(Post.id.in_(post.cross_posts)).all()
                                post.cross_posts.clear()
                                for ocp in old_cross_posts:
                                    if ocp.cross_posts is not None and post.id in ocp.cross_posts:
                                        ocp.cross_posts.remove(post.id)
                            delete_post_or_comment(user_ap_id, community_ap_id, to_be_deleted_ap_id)
                            activity_log.result = 'success'
                    elif request_json['object']['type'] == 'Page': # Sent for Mastodon's benefit
                        activity_log.result = 'ignored'
                        activity_log.exception_message = 'Intended for Mastodon'
                        db.session.add(activity_log)
                        db.session.commit()
                    elif request_json['object']['type'] == 'Note':  # Never sent?
                        activity_log.result = 'ignored'
                        activity_log.exception_message = 'Intended for Mastodon'
                        db.session.add(activity_log)
                        db.session.commit()
                    elif request_json['object']['type'] == 'Undo':
                        if request_json['object']['object']['type'] == 'Like' or request_json['object']['object']['type'] == 'Dislike':
                            activity_log.activity_type = request_json['object']['object']['type']
                            user_ap_id = request_json['object']['actor']
                            user = find_actor_or_create(user_ap_id)
                            post = None
                            comment = None
                            target_ap_id = request_json['object']['object']['object']           # object object object!
                            post = undo_vote(activity_log, comment, post, target_ap_id, user)
                            activity_log.result = 'success'
                        elif request_json['object']['object']['type'] == 'Delete':
                            if 'object' in request_json and 'object' in request_json['object']:
                                restore_post_or_comment(request_json['object']['object'])
                                activity_log.result = 'success'
                    elif request_json['object']['type'] == 'Add' and 'target' in request_json['object']:
                        activity_log.activity_type = request_json['object']['type']
                        target = request_json['object']['target']
                        community = Community.query.filter_by(ap_public_url=request_json['actor']).first()
                        if community:
                            featured_url = community.ap_featured_url
                            moderators_url = community.ap_moderators_url
                            if target == featured_url:
                                post = Post.query.filter_by(ap_id=request_json['object']['object']).first()
                                if post:
                                    post.sticky = True
                                    activity_log.result = 'success'
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
                                    activity_log.result = 'success'
                    elif request_json['object']['type'] == 'Remove' and 'target' in request_json['object']:
                        activity_log.activity_type = request_json['object']['type']
                        target = request_json['object']['target']
                        community = Community.query.filter_by(ap_public_url=request_json['actor']).first()
                        if community:
                            featured_url = community.ap_featured_url
                            moderators_url = community.ap_moderators_url
                            if target == featured_url:
                                post = Post.query.filter_by(ap_id=request_json['object']['object']).first()
                                if post:
                                    post.sticky = False
                                    activity_log.result = 'success'
                            if target == moderators_url:
                                user = find_actor_or_create(request_json['object']['object'], create_if_not_found=False)
                                if user:
                                    existing_membership = CommunityMember.query.filter_by(community_id=community.id, user_id=user.id).first()
                                    if existing_membership:
                                        existing_membership.is_moderator = False
                                    activity_log.result = 'success'
                    elif request_json['object']['type'] == 'Block' and 'target' in request_json['object']:
                        activity_log.activity_type = 'Community Ban'
                        mod_ap_id = request_json['object']['actor']
                        user_ap_id = request_json['object']['object']
                        target = request_json['object']['target']
                        remove_data = request_json['object']['removeData']
                        if target == request_json['actor'] and remove_data == True:
                            remove_data_from_banned_user(mod_ap_id, user_ap_id, target)
                        activity_log.result = 'success'
                    else:
                        activity_log.exception_message = 'Invalid type for Announce'

                        # Follow: remote user wants to join/follow one of our communities
                elif request_json['type'] == 'Follow':  # Follow is when someone wants to join a community
                    user_ap_id = request_json['actor']
                    community_ap_id = request_json['object']
                    follow_id = request_json['id']
                    user = find_actor_or_create(user_ap_id)
                    community = find_actor_or_create(community_ap_id, community_only=True)
                    if isinstance(community, Community):
                        if community and community.local_only and user:
                            activity_log.exception_message = 'Local only cannot be followed by remote users'

                            # send reject message to deny the follow
                            reject = {
                                "@context": default_context(),
                                "actor": community.public_url(),
                                "to": [
                                    user.public_url()
                                ],
                                "object": {
                                    "actor": user.public_url(),
                                    "to": None,
                                    "object": community.public_url(),
                                    "type": "Follow",
                                    "id": follow_id
                                },
                                    "type": "Reject",
                                    "id": f"https://{current_app.config['SERVER_NAME']}/activities/reject/" + gibberish(32)
                            }
                            # Lemmy doesn't yet understand Reject/Follow, so send without worrying about response for now.
                            post_request(user.ap_inbox_url, reject, community.private_key, f"{community.public_url()}#main-key")
                        else:
                            if user is not None and community is not None:
                                # check if user is banned from this community
                                banned = CommunityBan.query.filter_by(user_id=user.id, community_id=community.id).first()
                                if banned is None:
                                    user.last_seen = utcnow()
                                    if community_membership(user, community) != SUBSCRIPTION_MEMBER:
                                        member = CommunityMember(user_id=user.id, community_id=community.id)
                                        db.session.add(member)
                                        db.session.commit()
                                        cache.delete_memoized(community_membership, user, community)
                                    # send accept message to acknowledge the follow
                                    accept = {
                                        "@context": default_context(),
                                        "actor": community.public_url(),
                                        "to": [
                                            user.public_url()
                                        ],
                                        "object": {
                                            "actor": user.public_url(),
                                            "to": None,
                                            "object": community.public_url(),
                                            "type": "Follow",
                                            "id": follow_id
                                        },
                                        "type": "Accept",
                                        "id": f"https://{current_app.config['SERVER_NAME']}/activities/accept/" + gibberish(32)
                                    }
                                    if post_request(user.ap_inbox_url, accept, community.private_key, f"{community.public_url()}#main-key"):
                                        activity_log.result = 'success'
                                    else:
                                        activity_log.exception_message = 'Error sending Accept'
                                else:
                                    activity_log.exception_message = 'user is banned from this community'
                    elif isinstance(community, User):   # Pixelfed sends follow requests to the shared inbox, not the user inbox...
                        if current_app.debug:
                            process_user_follow_request(request_json, activity_log.id, user.id)
                        else:
                            process_user_follow_request.delay(request_json, activity_log.id, user.id)
                # Accept: remote server is accepting our previous follow request
                elif request_json['type'] == 'Accept':
                    if isinstance(request_json['object'], str): # a.gup.pe accepts using a string with the ID of the follow request
                        join_request_parts = request_json['object'].split('/')
                        join_request = CommunityJoinRequest.query.get(join_request_parts[-1])
                        existing_membership = CommunityMember.query.filter_by(user_id=join_request.user_id,
                                                                              community_id=join_request.community_id).first()
                        if not existing_membership:
                            member = CommunityMember(user_id=join_request.user_id, community_id=join_request.community_id)
                            db.session.add(member)
                            community.subscriptions_count += 1
                            db.session.commit()
                            cache.delete_memoized(community_membership, User.query.get(join_request.user_id), Community.query.get(join_request.community_id))
                        activity_log.result = 'success'
                    elif request_json['object']['type'] == 'Follow':
                        community_ap_id = request_json['actor']
                        user_ap_id = request_json['object']['actor']
                        user = find_actor_or_create(user_ap_id)
                        community = find_actor_or_create(community_ap_id, community_only=True)
                        if user and community:
                            join_request = CommunityJoinRequest.query.filter_by(user_id=user.id, community_id=community.id).first()
                            if join_request:
                                existing_membership = CommunityMember.query.filter_by(user_id=user.id, community_id=community.id).first()
                                if not existing_membership:
                                    member = CommunityMember(user_id=user.id, community_id=community.id)
                                    db.session.add(member)
                                    community.subscriptions_count += 1
                                    db.session.commit()
                                activity_log.result = 'success'
                                cache.delete_memoized(community_membership, user, community)

                elif request_json['type'] == 'Undo':
                    if request_json['object']['type'] == 'Follow':  # Unsubscribe from a community
                        community_ap_id = request_json['object']['object']
                        user_ap_id = request_json['object']['actor']
                        user = find_actor_or_create(user_ap_id)
                        community = find_actor_or_create(community_ap_id, community_only=True)
                        if user and community:
                            user.last_seen = utcnow()
                            member = CommunityMember.query.filter_by(user_id=user.id, community_id=community.id).first()
                            join_request = CommunityJoinRequest.query.filter_by(user_id=user.id, community_id=community.id).first()
                            if member:
                                db.session.delete(member)
                                community.subscriptions_count -= 1
                            if join_request:
                                db.session.delete(join_request)
                            db.session.commit()
                            cache.delete_memoized(community_membership, user, community)
                            activity_log.result = 'success'
                    elif request_json['object']['type'] == 'Like':  # Undoing an upvote or downvote
                        activity_log.activity_type = request_json['object']['type']
                        user_ap_id = request_json['actor']
                        user = find_actor_or_create(user_ap_id)
                        post = None
                        comment = None
                        target_ap_id = request_json['object']['object']
                        post_or_comment = undo_vote(activity_log, comment, post, target_ap_id, user)
                        if post_or_comment:
                            announce_activity_to_followers(post_or_comment.community, user, request_json)
                        activity_log.result = 'success'
                    elif request_json['object']['type'] == 'Dislike':  # Undoing a downvote - probably unused
                        activity_log.activity_type = request_json['object']['type']
                        user_ap_id = request_json['actor']
                        user = find_actor_or_create(user_ap_id)
                        post = None
                        comment = None
                        target_ap_id = request_json['object']['object']
                        post_or_comment = undo_downvote(activity_log, comment, post, target_ap_id, user)
                        if post_or_comment:
                            announce_activity_to_followers(post_or_comment.community, user, request_json)
                        activity_log.result = 'success'
                elif request_json['type'] == 'Delete':
                    if isinstance(request_json['object'], str):
                        ap_id = request_json['object']  # lemmy
                    else:
                        ap_id = request_json['object']['id']  # kbin
                    post = Post.query.filter_by(ap_id=ap_id).first()
                    # Delete post
                    if post:
                        if can_delete(request_json['actor'], post):
                            if post.url and post.cross_posts is not None:
                                old_cross_posts = Post.query.filter(Post.id.in_(post.cross_posts)).all()
                                post.cross_posts.clear()
                                for ocp in old_cross_posts:
                                    if ocp.cross_posts is not None:
                                        ocp.cross_posts.remove(post.id)
                            post.delete_dependencies()
                            announce_activity_to_followers(post.community, post.author, request_json)
                            post.deleted = True
                            db.session.commit()
                            activity_log.result = 'success'
                        else:
                            activity_log.exception_message = 'Delete attempt denied'
                    else:
                        # Delete PostReply
                        reply = PostReply.query.filter_by(ap_id=ap_id).first()
                        if reply:
                            if can_delete(request_json['actor'], reply):
                                reply.body_html = '<p><em>deleted</em></p>'
                                reply.body = 'deleted'
                                if not reply.author.bot:
                                    reply.post.reply_count -= 1
                                reply.deleted = True
                                announce_activity_to_followers(reply.community, reply.author, request_json)
                                db.session.commit()
                                activity_log.result = 'success'
                            else:
                                activity_log.exception_message = 'Delete attempt denied'
                        else:
                            # Delete User
                            user = find_actor_or_create(ap_id, create_if_not_found=False)
                            if user:
                                user.deleted = True
                                user.delete_dependencies()
                                db.session.commit()
                                activity_log.result = 'success'
                            else:
                                activity_log.exception_message = 'Delete: cannot find ' + ap_id

                elif request_json['type'] == 'Like' or request_json['type'] == 'EmojiReact':  # Upvote
                    activity_log.activity_type = request_json['type']
                    user_ap_id = request_json['actor']
                    user = find_actor_or_create(user_ap_id)
                    liked = find_liked_object(request_json['object'])
                    if user is None:
                        activity_log.exception_message = 'Blocked or unfound user'
                    elif liked is None:
                        activity_log.exception_message = 'Unfound object ' + request_json['object']
                    elif user.is_local():
                        activity_log.exception_message = 'Activity about local content which is already present'
                        activity_log.result = 'ignored'
                    elif can_upvote(user, liked.community):
                        # insert into voted table
                        if liked is None:
                            activity_log.exception_message = 'Liked object not found'
                        elif liked is not None and isinstance(liked, Post):
                            upvote_post(liked, user)
                            activity_log.result = 'success'
                        elif liked is not None and isinstance(liked, PostReply):
                            upvote_post_reply(liked, user)
                            activity_log.result = 'success'
                        else:
                            activity_log.exception_message = 'Could not detect type of like'
                        if activity_log.result == 'success':
                            announce_activity_to_followers(liked.community, user, request_json)
                    else:
                        activity_log.exception_message = 'Cannot upvote this'
                        activity_log.result = 'ignored'
                elif request_json['type'] == 'Dislike':  # Downvote
                    if get_setting('allow_dislike', True) is False:
                        activity_log.exception_message = 'Dislike ignored because of allow_dislike setting'
                    else:
                        activity_log.activity_type = request_json['type']
                        user_ap_id = request_json['actor']
                        user = find_actor_or_create(user_ap_id)
                        target_ap_id = request_json['object']
                        disliked = find_liked_object(target_ap_id)
                        if user is None:
                            activity_log.exception_message = 'Blocked or unfound user'
                        elif disliked is None:
                            activity_log.exception_message = 'Unfound object' + target_ap_id
                        elif user.is_local():
                            activity_log.exception_message = 'Activity about local content which is already present'
                            activity_log.result = 'ignored'
                        elif can_downvote(user, disliked.community, site):
                            # insert into voted table
                            if disliked is None:
                                activity_log.exception_message = 'Liked object not found'
                            elif isinstance(disliked, (Post, PostReply)):
                                if isinstance(disliked, Post):
                                    downvote_post(disliked, user)
                                elif isinstance(disliked, PostReply):
                                    downvote_post_reply(disliked, user)
                                activity_log.result = 'success'
                            else:
                                activity_log.exception_message = 'Could not detect type of like'
                            if activity_log.result == 'success':
                                announce_activity_to_followers(disliked.community, user, request_json)
                        else:
                            activity_log.exception_message = 'Cannot downvote this'
                            activity_log.result = 'ignored'
                elif request_json['type'] == 'Flag':    # Reported content
                    activity_log.activity_type = 'Report'
                    user_ap_id = request_json['actor']
                    user = find_actor_or_create(user_ap_id)
                    target_ap_id = request_json['object']
                    reported = find_reported_object(target_ap_id)
                    if user and reported:
                        process_report(user, reported, request_json, activity_log)
                        announce_activity_to_followers(reported.community, user, request_json)
                        activity_log.result = 'success'
                    else:
                        activity_log.exception_message = 'Report ignored due to missing user or content'
                elif request_json['type'] == 'Block':
                    activity_log.activity_type = 'Site Ban'
                    admin_ap_id = request_json['actor']
                    user_ap_id = request_json['object']
                    target = request_json['target']
                    remove_data = request_json['removeData']
                    if remove_data == True:
                        remove_data_from_banned_user(admin_ap_id, user_ap_id, target)
                    activity_log.result = 'success'

                    # Flush the caches of any major object that was created. To be sure.
                if 'user' in vars() and user is not None:
                    if user.instance_id and user.instance_id != 1:
                        user.instance.last_seen = utcnow()
                        # user.instance.ip_address = ip_address
                        user.instance.dormant = False
                        user.instance.gone_forever = False
                        user.instance.failures = 0
            else:
                activity_log.exception_message = 'Instance blocked'

            if activity_log.exception_message is not None and activity_log.result == 'processing':
                activity_log.result = 'failure'
            # Don't log successful json - save space
            if site.log_activitypub_json and activity_log.result == 'success' and not current_app.debug:
                activity_log.activity_json = ''
            db.session.commit()


@celery.task
def process_delete_request(request_json, activitypublog_id, ip_address):
    with current_app.app_context():
        activity_log = ActivityPubLog.query.get(activitypublog_id)
        if 'type' in request_json and request_json['type'] == 'Delete':
            if isinstance(request_json['object'], dict):
                # wafrn sends invalid delete requests
                return
            else:
                actor_to_delete = request_json['object'].lower()
                user = User.query.filter_by(ap_profile_id=actor_to_delete).first()
                if user:
                    # check that the user really has been deleted, to avoid spoofing attacks
                    if not user.is_local():
                        if user_removed_from_remote_server(actor_to_delete, is_piefed=user.instance.software == 'PieFed'):
                            # Delete all their images to save moderators from having to see disgusting stuff.
                            files = File.query.join(Post).filter(Post.user_id == user.id).all()
                            for file in files:
                                file.delete_from_disk()
                                file.source_url = ''
                            if user.avatar_id:
                                user.avatar.delete_from_disk()
                                user.avatar.source_url = ''
                            if user.cover_id:
                                user.cover.delete_from_disk()
                                user.cover.source_url = ''
                            user.banned = True
                            user.deleted = True
                            activity_log.result = 'success'
                        else:
                            activity_log.result = 'ignored'
                            activity_log.exception_message = 'User not actually deleted.'
                    else:
                        activity_log.result = 'ignored'
                        activity_log.exception_message = 'Only remote users can be deleted remotely'
                else:
                    activity_log.result = 'ignored'
                    activity_log.exception_message = 'Does not exist here'
                db.session.commit()


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


@bp.route('/u/<actor>/inbox', methods=['POST'])
def user_inbox(actor):
    site = Site.query.get(1)
    activity_log = ActivityPubLog(direction='in', result='failure')
    activity_log.result = 'processing'
    db.session.add(activity_log)
    db.session.commit()

    try:
        request_json = request.get_json(force=True)
    except werkzeug.exceptions.BadRequest as e:
        activity_log.exception_message = 'Unable to parse json body: ' + e.description
        activity_log.result = 'failure'
        db.session.commit()
        return '', 400

    if 'id' in request_json:
        activity_log.activity_id = request_json['id']
    if site.log_activitypub_json:
        activity_log.activity_json = json.dumps(request_json)

    actor = find_actor_or_create(request_json['actor'], signed_get=True) if 'actor' in request_json else None
    if actor is not None:
        if (('type' in request_json and request_json['type'] == 'Like') or
                ('type' in request_json and request_json['type'] == 'Undo' and
                'object' in request_json and request_json['object']['type'] == 'Like')):
            return shared_inbox()
        if 'type' in request_json and request_json['type'] == 'Accept':
            return shared_inbox()
        try:
            HttpSignature.verify_request(request, actor.public_key, skip_date=True)
            if 'type' in request_json:
                if request_json['type'] == 'Follow':
                    if current_app.debug:
                        process_user_follow_request(request_json, activity_log.id, actor.id)
                    else:
                        process_user_follow_request.delay(request_json, activity_log.id, actor.id)
                elif request_json['type'] == 'Undo' and 'object' in request_json and request_json['object']['type'] == 'Follow':
                    local_user_ap_id = request_json['object']['object']
                    local_user = find_actor_or_create(local_user_ap_id, create_if_not_found=False)
                    remote_user = User.query.get(actor.id)
                    if local_user:
                        db.session.query(UserFollower).filter_by(local_user_id=local_user.id, remote_user_id=remote_user.id, is_accepted=True).delete()
                        activity_log.result = 'success'
                    else:
                        activity_log.exception_message = 'Could not find local user'
                        activity_log.result = 'failure'
                    db.session.commit()
                elif ('type' in request_json and request_json['type'] == 'Create' and
                    'object' in request_json and request_json['object']['type'] == 'Note' and
                    'name' in request_json['object']):                                              # poll votes
                    in_reply_to = request_json['object']['inReplyTo'] if 'inReplyTo' in request_json['object'] else None
                    if in_reply_to:
                        post_being_replied_to = Post.query.filter_by(ap_id=request_json['object']['inReplyTo']).first()
                        if post_being_replied_to:
                            community_ap_id = post_being_replied_to.community.ap_profile_id
                            community = find_actor_or_create(community_ap_id, community_only=True, create_if_not_found=False)
                            user_ap_id = request_json['object']['attributedTo']
                            user = find_actor_or_create(user_ap_id, create_if_not_found=False)
                            if can_create_post_reply(user, community):
                                poll_data = Poll.query.get(post_being_replied_to.id)
                                choice = PollChoice.query.filter_by(post_id=post_being_replied_to.id, choice_text=request_json['object']['name']).first()
                                if poll_data and choice:
                                    poll_data.vote_for_choice(choice.id, user.id)
                                    activity_log.activity_type = 'Poll Vote'
                                    activity_log.result = 'success'
                                    db.session.commit()
                                    if post_being_replied_to.author.is_local():
                                        inform_followers_of_post_update(post_being_replied_to.id, user.instance_id)

        except VerificationError:
            activity_log.result = 'failure'
            activity_log.exception_message = 'Could not verify signature'
            db.session.commit()
            return '', 400
    else:
        actor_name = request_json['actor'] if 'actor' in request_json else ''
        activity_log.exception_message = f'Actor could not be found: {actor_name}'

    if activity_log.exception_message is not None:
        activity_log.result = 'failure'
        db.session.commit()
    resp = jsonify('ok')
    resp.content_type = 'application/activity+json'
    return resp


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
                local_user.ap_followers_url = local_user.ap_public_url + '/followers'
            db.session.add(new_follower)
        accept = {
            "@context": default_context(),
            "actor": local_user.ap_profile_id,
            "to": [
                remote_user.ap_profile_id
            ],
            "object": {
                "actor": remote_user.ap_profile_id,
                "to": None,
                "object": local_user.ap_profile_id,
                "type": "Follow",
                "id": follow_id
            },
            "type": "Accept",
            "id": f"https://{current_app.config['SERVER_NAME']}/activities/accept/" + gibberish(32)
        }
        if post_request(remote_user.ap_inbox_url, accept, local_user.private_key, f"{local_user.public_url()}#main-key"):
            activity_log.result = 'success'
        else:
            activity_log.exception_message = 'Error sending Accept'
    else:
        activity_log.exception_message = 'Could not find local user'
        activity_log.result = 'failure'

    db.session.commit()


@bp.route('/c/<actor>/inbox', methods=['GET', 'POST'])
def community_inbox(actor):
    return shared_inbox()


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


@bp.route('/comment/<int:comment_id>', methods=['GET'])
def comment_ap(comment_id):
    if is_activitypub_request():
        reply = PostReply.query.get_or_404(comment_id)
        reply_data = comment_model_to_json(reply)
        resp = jsonify(reply_data)
        resp.content_type = 'application/activity+json'
        resp.headers.set('Vary', 'Accept')
        return resp
    else:
        reply = PostReply.query.get_or_404(comment_id)
        return continue_discussion(reply.post.id, comment_id)


@bp.route('/post/<int:post_id>/', methods=['GET'])
def post_ap2(post_id):
    return redirect(url_for('activitypub.post_ap', post_id=post_id))


@bp.route('/post/<int:post_id>', methods=['GET', 'POST'])
@cache.cached(timeout=3, make_cache_key=make_cache_key)
def post_ap(post_id):
    if request.method == 'GET' and is_activitypub_request():
        post = Post.query.get_or_404(post_id)
        post_data = post_to_page(post)
        post_data['@context'] = default_context()
        resp = jsonify(post_data)
        resp.content_type = 'application/activity+json'
        resp.headers.set('Vary', 'Accept')
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
