import base64
import os
from collections import namedtuple
from io import BytesIO
from random import randint

import flask
from PIL import Image, ImageOps
from flask import redirect, url_for, flash, request, make_response, session, Markup, current_app, abort, g, json, \
    jsonify
from flask_login import current_user, login_required
from flask_babel import _
from pillow_heif import register_heif_opener
from slugify import slugify
from sqlalchemy import or_, desc, text

from app import db, constants, cache, celery
from app.activitypub.signature import RsaKeys, post_request, default_context, post_request_in_background
from app.activitypub.util import notify_about_post, make_image_sizes, resolve_remote_post, extract_domain_and_actor
from app.chat.util import send_message
from app.community.forms import SearchRemoteCommunity, CreateDiscussionForm, CreateImageForm, CreateLinkForm, \
    ReportCommunityForm, \
    DeleteCommunityForm, AddCommunityForm, EditCommunityForm, AddModeratorForm, BanUserCommunityForm, \
    EscalateReportForm, ResolveReportForm, CreateVideoForm, CreatePollForm, RetrieveRemotePost, \
    EditCommunityWikiPageForm
from app.community.util import search_for_community, actor_to_community, \
    save_post, save_icon_file, save_banner_file, send_to_remote_instance, \
    delete_post_from_community, delete_post_reply_from_community, community_in_list, find_local_users, tags_from_string, \
    allowed_extensions, end_poll_date
from app.constants import SUBSCRIPTION_MEMBER, SUBSCRIPTION_OWNER, POST_TYPE_LINK, POST_TYPE_ARTICLE, POST_TYPE_IMAGE, \
    SUBSCRIPTION_PENDING, SUBSCRIPTION_MODERATOR, REPORT_STATE_NEW, REPORT_STATE_ESCALATED, REPORT_STATE_RESOLVED, \
    REPORT_STATE_DISCARDED, POST_TYPE_VIDEO, NOTIF_COMMUNITY, NOTIF_POST, POST_TYPE_POLL, MICROBLOG_APPS
from app.inoculation import inoculation
from app.models import User, Community, CommunityMember, CommunityJoinRequest, CommunityBan, Post, \
    File, PostVote, utcnow, Report, Notification, InstanceBlock, ActivityPubLog, Topic, Conversation, PostReply, \
    NotificationSubscription, UserFollower, Instance, Language, Poll, PollChoice, ModLog, CommunityWikiPage, \
    CommunityWikiPageRevision, read_posts
from app.community import bp
from app.user.utils import search_for_user
from app.utils import get_setting, render_template, allowlist_html, markdown_to_html, validation_required, \
    shorten_string, gibberish, community_membership, ap_datetime, \
    request_etag_matches, return_304, instance_banned, can_create_post, can_upvote, can_downvote, user_filters_posts, \
    joined_communities, moderating_communities, blocked_domains, mimetype_from_url, blocked_instances, \
    community_moderators, communities_banned_from, show_ban_message, recently_upvoted_posts, recently_downvoted_posts, \
    blocked_users, languages_for_form, menu_topics, add_to_modlog, \
    blocked_communities, remove_tracking_from_link, piefed_markdown_to_lemmy_markdown, ensure_directory_exists
from feedgen.feed import FeedGenerator
from datetime import timezone, timedelta
from copy import copy


@bp.route('/add_local', methods=['GET', 'POST'])
@login_required
def add_local():
    if current_user.banned:
        return show_ban_message()
    form = AddCommunityForm()
    if g.site.enable_nsfw is False:
        form.nsfw.render_kw = {'disabled': True}

    form.languages.choices = languages_for_form()

    if form.validate_on_submit():
        if form.url.data.strip().lower().startswith('/c/'):
            form.url.data = form.url.data[3:]
        form.url.data = slugify(form.url.data.strip(), separator='_').lower()
        private_key, public_key = RsaKeys.generate_keypair()
        community = Community(title=form.community_name.data, name=form.url.data, description=piefed_markdown_to_lemmy_markdown(form.description.data),
                              rules=form.rules.data, nsfw=form.nsfw.data, private_key=private_key,
                              public_key=public_key, description_html=markdown_to_html(form.description.data),
                              rules_html=markdown_to_html(form.rules.data), local_only=form.local_only.data,
                              ap_profile_id='https://' + current_app.config['SERVER_NAME'] + '/c/' + form.url.data.lower(),
                              ap_public_url='https://' + current_app.config['SERVER_NAME'] + '/c/' + form.url.data,
                              ap_followers_url='https://' + current_app.config['SERVER_NAME'] + '/c/' + form.url.data + '/followers',
                              ap_domain=current_app.config['SERVER_NAME'],
                              subscriptions_count=1, instance_id=1, low_quality='memes' in form.url.data)
        icon_file = request.files['icon_file']
        if icon_file and icon_file.filename != '':
            file = save_icon_file(icon_file)
            if file:
                community.icon = file
        banner_file = request.files['banner_file']
        if banner_file and banner_file.filename != '':
            file = save_banner_file(banner_file)
            if file:
                community.image = file
        db.session.add(community)
        db.session.commit()
        membership = CommunityMember(user_id=current_user.id, community_id=community.id, is_moderator=True,
                                     is_owner=True)
        db.session.add(membership)
        # Languages of the community
        for language_choice in form.languages.data:
            community.languages.append(Language.query.get(language_choice))
        # Always include the undetermined language, so posts with no language will be accepted
        community.languages.append(Language.query.filter(Language.code == 'und').first())
        db.session.commit()
        flash(_('Your new community has been created.'))
        cache.delete_memoized(community_membership, current_user, community)
        cache.delete_memoized(joined_communities, current_user.id)
        cache.delete_memoized(moderating_communities, current_user.id)
        return redirect('/c/' + community.name)

    return render_template('community/add_local.html', title=_('Create community'), form=form, moderating_communities=moderating_communities(current_user.get_id()),
                           joined_communities=joined_communities(current_user.get_id()),
                           current_app=current_app,
                           menu_topics=menu_topics(),
                           site=g.site)


@bp.route('/add_remote', methods=['GET', 'POST'])
@login_required
def add_remote():
    if current_user.banned:
        return show_ban_message()
    form = SearchRemoteCommunity()
    new_community = None
    if form.validate_on_submit():
        address = form.address.data.strip().lower()
        if address.startswith('!') and '@' in address:
            try:
                new_community = search_for_community(address)
            except Exception as e:
                if 'is blocked.' in str(e):
                    flash(_('Sorry, that instance is blocked, check https://gui.fediseer.com/ for reasons.'), 'warning')
        elif address.startswith('@') and '@' in address[1:]:
            # todo: the user is searching for a person instead
            ...
        elif '@' in address:
            new_community = search_for_community('!' + address)
        elif address.startswith('https://'):
            server, community = extract_domain_and_actor(address)
            new_community = search_for_community('!' + community + '@' + server)
        else:
            message = Markup(
                'Accepted address formats: !community@server.name or https://server.name/{c|m}/community. Search on <a href="https://lemmyverse.net/communities">Lemmyverse.net</a> to find some.')
            flash(message, 'error')
        if new_community is None:
            if g.site.enable_nsfw:
                flash(_('Community not found.'), 'warning')
            else:
                flash(_('Community not found. If you are searching for a nsfw community it is blocked by this instance.'), 'warning')
        else:
            if new_community.banned:
                flash(_('That community is banned from %(site)s.', site=g.site.name), 'warning')

    return render_template('community/add_remote.html',
                           title=_('Add remote community'), form=form, new_community=new_community,
                           subscribed=community_membership(current_user, new_community) >= SUBSCRIPTION_MEMBER, moderating_communities=moderating_communities(current_user.get_id()),
                           joined_communities=joined_communities(current_user.get_id()),
                           menu_topics=menu_topics(),
                           site=g.site)


@bp.route('/retrieve_remote_post/<int:community_id>', methods=['GET', 'POST'])
@login_required
def retrieve_remote_post(community_id: int):
    if current_user.banned:
        return show_ban_message()
    form = RetrieveRemotePost()
    new_post = None
    community = Community.query.get_or_404(community_id)
    if form.validate_on_submit():
        address = form.address.data.strip()
        new_post = resolve_remote_post(address, community_id)
        if new_post is None:
            flash(_('Post not found.'), 'warning')

    return render_template('community/retrieve_remote_post.html',
                           title=_('Retrieve Remote Post'), form=form, new_post=new_post, community=community)


# @bp.route('/c/<actor>', methods=['GET']) - defined in activitypub/routes.py, which calls this function for user requests. A bit weird.
def show_community(community: Community):

    if community.banned:
        abort(404)

    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', '' if current_user.is_anonymous else current_user.default_sort)
    if sort is None:
        sort = ''
    low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'
    if low_bandwidth:
        post_layout = None
    else:
        if community.default_layout is not None and community.default_layout != '':
            post_layout = request.args.get('layout', community.default_layout)
        else:
            post_layout = request.args.get('layout', 'list')

    # If nothing has changed since their last visit, return HTTP 304
    current_etag = f"{community.id}{sort}{post_layout}_{hash(community.last_active)}"
    if current_user.is_anonymous and request_etag_matches(current_etag):
        return return_304(current_etag)

    mods = community_moderators(community.id)

    if current_user.is_authenticated and community.id not in communities_banned_from(current_user.id):
        is_moderator = any(mod.user_id == current_user.id for mod in mods)
        is_owner = any(mod.user_id == current_user.id and mod.is_owner == True for mod in mods)
        is_admin = current_user.is_admin()
    else:
        is_moderator = False
        is_owner = False
        is_admin = False

    # Build list of moderators and set un-moderated flag
    mod_user_ids = [mod.user_id for mod in mods]
    un_moderated = False
    if community.private_mods:
        mod_list = []
        inactive_mods = User.query.filter(User.id.in_(mod_user_ids), User.last_seen < utcnow() - timedelta(days=60)).all()
    else:
        mod_list = User.query.filter(User.id.in_(mod_user_ids)).all()
        inactive_mods = []
        for mod in mod_list:
            if mod.last_seen < utcnow() - timedelta(days=60):
                inactive_mods.append(mod)
    if current_user.is_authenticated and (current_user.is_admin() or current_user.is_staff()):
        un_moderated = len(mod_user_ids) == len(inactive_mods)

    posts = community.posts

    # filter out nsfw and nsfl if desired
    if current_user.is_anonymous:
        posts = posts.filter(Post.from_bot == False, Post.nsfw == False, Post.nsfl == False, Post.deleted == False)
        content_filters = {}
    else:
        if current_user.ignore_bots == 1:
            posts = posts.filter(Post.from_bot == False)
        if current_user.hide_nsfl == 1:
            posts = posts.filter(Post.nsfl == False)
        if current_user.hide_nsfw == 1:
            posts = posts.filter(Post.nsfw == False)
        if current_user.hide_read_posts:
            posts = posts.outerjoin(read_posts, (Post.id == read_posts.c.read_post_id) & (read_posts.c.user_id == current_user.id))
            posts = posts.filter(read_posts.c.read_post_id.is_(None))  # Filter where there is no corresponding read post for the current user
        content_filters = user_filters_posts(current_user.id)
        posts = posts.filter(Post.deleted == False)

        # filter domains and instances
        domains_ids = blocked_domains(current_user.id)
        if domains_ids:
            posts = posts.filter(or_(Post.domain_id.not_in(domains_ids), Post.domain_id == None))
        instance_ids = blocked_instances(current_user.id)
        if instance_ids:
            posts = posts.filter(or_(Post.instance_id.not_in(instance_ids), Post.instance_id == None))
        community_ids = blocked_communities(current_user.id)
        if community_ids:
            posts = posts.filter(Post.community_id.not_in(community_ids))

        # filter blocked users
        blocked_accounts = blocked_users(current_user.id)
        if blocked_accounts:
            posts = posts.filter(Post.user_id.not_in(blocked_accounts))

    if sort == '' or sort == 'hot':
        posts = posts.order_by(desc(Post.sticky)).order_by(desc(Post.ranking)).order_by(desc(Post.posted_at))
    elif sort == 'top':
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=7)).order_by(desc(Post.sticky)).order_by(desc(Post.up_votes - Post.down_votes))
    elif sort == 'new':
        posts = posts.order_by(desc(Post.posted_at))
    elif sort == 'active':
        posts = posts.order_by(desc(Post.sticky)).order_by(desc(Post.last_active))
    per_page = 100
    if post_layout == 'masonry':
        per_page = 200
    elif post_layout == 'masonry_wide':
        per_page = 300
    posts = posts.paginate(page=page, per_page=per_page, error_out=False)

    breadcrumbs = []
    breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
    breadcrumb.text = _('Home')
    breadcrumb.url = '/'
    breadcrumbs.append(breadcrumb)

    if community.topic_id:
        related_communities = Community.query.filter_by(topic_id=community.topic_id).\
            filter(Community.id != community.id, Community.banned == False).order_by(Community.name)
        topics = []
        previous_topic = Topic.query.get(community.topic_id)
        topics.append(previous_topic)
        while previous_topic.parent_id:
            topic = Topic.query.get(previous_topic.parent_id)
            topics.append(topic)
            previous_topic = topic
        topics = list(reversed(topics))

        breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
        breadcrumb.text = _('Topics')
        breadcrumb.url = '/topics'
        breadcrumbs.append(breadcrumb)

        existing_url = '/topic'
        for topic in topics:
            breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
            breadcrumb.text = topic.name
            breadcrumb.url = f"{existing_url}/{topic.machine_name}"
            breadcrumbs.append(breadcrumb)
            existing_url = breadcrumb.url
    else:
        related_communities = []
        breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
        breadcrumb.text = _('Communities')
        breadcrumb.url = '/communities'
        breadcrumbs.append(breadcrumb)

    description = shorten_string(community.description, 150) if community.description else None
    og_image = community.image.source_url if community.image_id else None

    next_url = url_for('activitypub.community_profile', actor=community.ap_id if community.ap_id is not None else community.name,
                       page=posts.next_num, sort=sort, layout=post_layout) if posts.has_next else None
    prev_url = url_for('activitypub.community_profile', actor=community.ap_id if community.ap_id is not None else community.name,
                       page=posts.prev_num, sort=sort, layout=post_layout) if posts.has_prev and page != 1 else None

    # Voting history
    if current_user.is_authenticated:
        recently_upvoted = recently_upvoted_posts(current_user.id)
        recently_downvoted = recently_downvoted_posts(current_user.id)
    else:
        recently_upvoted = []
        recently_downvoted = []

    return render_template('community/community.html', community=community, title=community.title, breadcrumbs=breadcrumbs,
                           is_moderator=is_moderator, is_owner=is_owner, is_admin=is_admin, mods=mod_list, posts=posts, description=description,
                           og_image=og_image, POST_TYPE_IMAGE=POST_TYPE_IMAGE, POST_TYPE_LINK=POST_TYPE_LINK,
                           POST_TYPE_VIDEO=POST_TYPE_VIDEO, POST_TYPE_POLL=POST_TYPE_POLL, SUBSCRIPTION_PENDING=SUBSCRIPTION_PENDING,
                           SUBSCRIPTION_MEMBER=SUBSCRIPTION_MEMBER, SUBSCRIPTION_OWNER=SUBSCRIPTION_OWNER, SUBSCRIPTION_MODERATOR=SUBSCRIPTION_MODERATOR,
                           etag=f"{community.id}{sort}{post_layout}_{hash(community.last_active)}", related_communities=related_communities,
                           next_url=next_url, prev_url=prev_url, low_bandwidth=low_bandwidth, un_moderated=un_moderated,
                           recently_upvoted=recently_upvoted, recently_downvoted=recently_downvoted,
                           rss_feed=f"https://{current_app.config['SERVER_NAME']}/community/{community.link()}/feed", rss_feed_name=f"{community.title} on {g.site.name}",
                           content_filters=content_filters, moderating_communities=moderating_communities(current_user.get_id()),
                           joined_communities=joined_communities(current_user.get_id()),
                           menu_topics=menu_topics(), site=g.site, sort=sort,
                           inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None,
                           post_layout=post_layout, current_app=current_app)


# RSS feed of the community
@bp.route('/<actor>/feed', methods=['GET'])
@cache.cached(timeout=600)
def show_community_rss(actor):
    actor = actor.strip()
    if '@' in actor:
        community: Community = Community.query.filter_by(ap_id=actor, banned=False).first()
    else:
        community: Community = Community.query.filter_by(name=actor, banned=False, ap_id=None).first()
    if community is not None:
        # If nothing has changed since their last visit, return HTTP 304
        current_etag = f"{community.id}_{hash(community.last_active)}"
        if request_etag_matches(current_etag):
            return return_304(current_etag, 'application/rss+xml')

        posts = community.posts.filter(Post.from_bot == False, Post.deleted == False).order_by(desc(Post.created_at)).limit(100).all()
        description = shorten_string(community.description, 150) if community.description else None
        og_image = community.image.source_url if community.image_id else None
        fg = FeedGenerator()
        fg.id(f"https://{current_app.config['SERVER_NAME']}/c/{actor}")
        fg.title(f'{community.title} on {g.site.name}')
        fg.link(href=f"https://{current_app.config['SERVER_NAME']}/c/{actor}", rel='alternate')
        if og_image:
            fg.logo(og_image)
        else:
            fg.logo(f"https://{current_app.config['SERVER_NAME']}/static/images/apple-touch-icon.png")
        if description:
            fg.subtitle(description)
        else:
            fg.subtitle(' ')
        fg.link(href=f"https://{current_app.config['SERVER_NAME']}/c/{actor}/feed", rel='self')
        fg.language('en')

        for post in posts:
            fe = fg.add_entry()
            fe.title(post.title)
            fe.link(href=f"https://{current_app.config['SERVER_NAME']}/post/{post.id}")
            if post.url:
                type = mimetype_from_url(post.url)
                if type and not type.startswith('text/'):
                    fe.enclosure(post.url, type=type)
            fe.description(post.body_html)
            fe.guid(post.profile_id(), permalink=True)
            fe.author(name=post.author.user_name)
            fe.pubDate(post.created_at.replace(tzinfo=timezone.utc))

        response = make_response(fg.rss_str())
        response.headers.set('Content-Type', 'application/rss+xml')
        response.headers.add_header('ETag', f"{community.id}_{hash(community.last_active)}")
        response.headers.add_header('Cache-Control', 'no-cache, max-age=600, must-revalidate')
        return response
    else:
        abort(404)


@bp.route('/<actor>/subscribe', methods=['GET'])
@login_required
@validation_required
def subscribe(actor):
    do_subscribe(actor, current_user.id)
    referrer = request.headers.get('Referer', None)
    if referrer is not None:
        return redirect(referrer)
    else:
        return redirect('/c/' + actor)


# this is separated out from the subscribe route so it can be used by the 
# admin.admin_federation.preload_form as well
@celery.task
def do_subscribe(actor, user_id, admin_preload=False):
    remote = False
    actor = actor.strip()
    user = User.query.get(user_id)
    pre_load_message = {}
    if '@' in actor:
        community = Community.query.filter_by(banned=False, ap_id=actor).first()
        remote = True
    else:
        community = Community.query.filter_by(name=actor, banned=False, ap_id=None).first()

    if community is not None:
        pre_load_message['community'] = community.ap_id
        if community.id in communities_banned_from(user.id):
            if not admin_preload:
                abort(401)
            else:
                pre_load_message['user_banned'] = True
        if community_membership(user, community) != SUBSCRIPTION_MEMBER and community_membership(user, community) != SUBSCRIPTION_PENDING:
            banned = CommunityBan.query.filter_by(user_id=user.id, community_id=community.id).first()
            if banned:
                if not admin_preload:
                    flash(_('You cannot join this community'))
                else:
                    pre_load_message['community_banned_by_local_instance'] = True
            success = True
            if remote:
                # send ActivityPub message to remote community, asking to follow. Accept message will be sent to our shared inbox
                join_request = CommunityJoinRequest(user_id=user.id, community_id=community.id)
                db.session.add(join_request)
                db.session.commit()
                if community.instance.online():
                    follow = {
                      "actor": user.public_url(),
                      "to": [community.public_url()],
                      "object": community.public_url(),
                      "type": "Follow",
                      "id": f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
                    }
                    success = post_request(community.ap_inbox_url, follow, user.private_key,
                                                           user.public_url() + '#main-key', timeout=10)
                if success is False or isinstance(success, str):
                    if 'is not in allowlist' in success:
                        msg_to_user = f'{community.instance.domain} does not allow us to join their communities.'
                        if not admin_preload:
                            flash(_(msg_to_user), 'error')
                        else:
                            pre_load_message['status'] = msg_to_user
                    else:
                        msg_to_user = "There was a problem while trying to communicate with remote server. If other people have already joined this community it won't matter."
                        if not admin_preload:
                            flash(_(msg_to_user), 'error')
                        else:
                            pre_load_message['status'] = msg_to_user

            # for local communities, joining is instant
            member = CommunityMember(user_id=user.id, community_id=community.id)
            db.session.add(member)
            db.session.commit()
            if success is True:
                if not admin_preload:
                    flash('You joined ' + community.title)
                else:
                    pre_load_message['status'] = 'joined'
        else:
            if admin_preload:
                pre_load_message['status'] = 'already subscribed, or subsciption pending'

        cache.delete_memoized(community_membership, user, community)
        cache.delete_memoized(joined_communities, user.id)
        if admin_preload:
            return pre_load_message
    else:
        if not admin_preload:
            abort(404)
        else:
            pre_load_message['community'] = actor
            pre_load_message['status'] = 'community not found'
            return pre_load_message


@bp.route('/<actor>/unsubscribe', methods=['GET'])
@login_required
def unsubscribe(actor):
    community = actor_to_community(actor)

    if community is not None:
        subscription = community_membership(current_user, community)
        if subscription:
            if subscription != SUBSCRIPTION_OWNER:
                proceed = True
                # Undo the Follow
                if '@' in actor:    # this is a remote community, so activitypub is needed
                    success = True
                    if not community.instance.gone_forever:
                        follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{gibberish(15)}"
                        if community.instance.domain == 'a.gup.pe':
                            join_request = CommunityJoinRequest.query.filter_by(user_id=current_user.id, community_id=community.id).first()
                            if join_request:
                                follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
                        undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/" + gibberish(15)
                        follow = {
                          "actor": current_user.public_url(),
                          "to": [community.public_url()],
                          "object": community.public_url(),
                          "type": "Follow",
                          "id": follow_id
                        }
                        undo = {
                          'actor': current_user.public_url(),
                          'to': [community.public_url()],
                          'type': 'Undo',
                          'id': undo_id,
                          'object': follow
                        }
                        success = post_request(community.ap_inbox_url, undo, current_user.private_key,
                                                               current_user.public_url() + '#main-key', timeout=10)
                    if success is False or isinstance(success, str):
                        flash('There was a problem while trying to unsubscribe', 'error')

                if proceed:
                    db.session.query(CommunityMember).filter_by(user_id=current_user.id, community_id=community.id).delete()
                    db.session.query(CommunityJoinRequest).filter_by(user_id=current_user.id, community_id=community.id).delete()
                    db.session.commit()

                    flash('You have left ' + community.title)
                cache.delete_memoized(community_membership, current_user, community)
                cache.delete_memoized(joined_communities, current_user.id)
            else:
                # todo: community deletion
                flash('You need to make someone else the owner before unsubscribing.', 'warning')

        # send them back where they came from
        referrer = request.headers.get('Referer', None)
        if referrer is not None:
            return redirect(referrer)
        else:
            return redirect('/c/' + actor)
    else:
        abort(404)


@bp.route('/<actor>/join_then_add', methods=['GET', 'POST'])
@login_required
@validation_required
def join_then_add(actor):
    community = actor_to_community(actor)
    if not current_user.subscribed(community.id):
        if not community.is_local():
            # send ActivityPub message to remote community, asking to follow. Accept message will be sent to our shared inbox
            join_request = CommunityJoinRequest(user_id=current_user.id, community_id=community.id)
            db.session.add(join_request)
            db.session.commit()
            if not community.instance.gone_forever:
                follow = {
                  "actor": current_user.public_url(),
                  "to": [community.public_url()],
                  "object": community.public_url(),
                  "type": "Follow",
                  "id": f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
                }
                post_request(community.ap_inbox_url, follow, current_user.private_key,
                                            current_user.public_url() + '#main-key')
        member = CommunityMember(user_id=current_user.id, community_id=community.id)
        db.session.add(member)
        db.session.commit()
        flash('You joined ' + community.title)
    if not community.user_is_banned(current_user):
        return redirect(url_for('community.add_post', actor=community.link(), type='discussion'))
    else:
        abort(401)


@bp.route('/<actor>/submit/<string:type>', methods=['GET', 'POST'])
@bp.route('/<actor>/submit', defaults={'type': 'discussion'}, methods=['GET', 'POST'])
@login_required
@validation_required
def add_post(actor, type):
    if current_user.banned:
        return show_ban_message()
    community = actor_to_community(actor)

    post_type = POST_TYPE_ARTICLE
    if type == 'discussion':
        form = CreateDiscussionForm()
    elif type == 'link':
        post_type = POST_TYPE_LINK
        form = CreateLinkForm()
    elif type == 'image':
        post_type = POST_TYPE_IMAGE
        form = CreateImageForm()
    elif type == 'video':
        post_type = POST_TYPE_VIDEO
        form = CreateVideoForm()
    elif type == 'poll':
        post_type = POST_TYPE_POLL
        form = CreatePollForm()
    else:
        abort(404)

    if g.site.enable_nsfl is False:
        form.nsfl.render_kw = {'disabled': True}
    if community.nsfw:
        form.nsfw.data = True
        form.nsfw.render_kw = {'disabled': True}
    if community.nsfl:
        form.nsfl.data = True
        form.nsfw.render_kw = {'disabled': True}
    if not(community.is_moderator() or community.is_owner() or current_user.is_admin()):
        form.sticky.render_kw = {'disabled': True}

    form.communities.choices = [(c.id, c.display_name()) for c in current_user.communities()]
    if not community_in_list(community.id, form.communities.choices):
        form.communities.choices.append((community.id, community.display_name()))

    form.language_id.choices = languages_for_form()

    if not can_create_post(current_user, community):
        abort(401)

    if form.validate_on_submit():
        community = Community.query.get_or_404(form.communities.data)
        if not can_create_post(current_user, community):
            abort(401)

        language = Language.query.get(form.language_id.data)

        request_json = {
            'id': None,
            'object': {
                'name': form.title.data,
                'type': 'Page',
                'sticky': form.sticky.data,
                'nsfw': form.nsfw.data,
                'nsfl': form.nsfl.data,
                'id': gibberish(),   # this will  be updated once we have the post.id
                'mediaType': 'text/markdown',
                'content': form.body.data,
                'tag': tags_from_string(form.tags.data),
                'language': {'identifier': language.code, 'name': language.name}
            }
        }
        if type == 'link':
            request_json['object']['attachment'] = [{'type': 'Link', 'href': form.link_url.data}]
        elif type == 'image':
            uploaded_file = request.files['image_file']
            if uploaded_file and uploaded_file.filename != '':
                # check if this is an allowed type of file
                file_ext = os.path.splitext(uploaded_file.filename)[1]
                if file_ext.lower() not in allowed_extensions:
                    abort(400, description="Invalid image type.")

                new_filename = gibberish(15)
                # set up the storage directory
                directory = 'app/static/media/posts/' + new_filename[0:2] + '/' + new_filename[2:4]
                ensure_directory_exists(directory)

                final_place = os.path.join(directory, new_filename + file_ext)
                uploaded_file.seek(0)
                uploaded_file.save(final_place)

                if file_ext.lower() == '.heic':
                    register_heif_opener()

                Image.MAX_IMAGE_PIXELS = 89478485

                # resize if necessary
                img = Image.open(final_place)
                if '.' + img.format.lower() in allowed_extensions:
                    img = ImageOps.exif_transpose(img)

                    # limit full sized version to 2000px
                    img.thumbnail((2000, 2000))
                    img.save(final_place)

                request_json['object']['attachment'] = [{'type': 'Image', 'url': f'https://{current_app.config["SERVER_NAME"]}/{final_place.replace("app/", "")}',
                                                        'name': form.image_alt_text.data}]
        elif type == 'video':
            request_json['object']['attachment'] = [{'type': 'Document', 'url': form.video_url.data}]
        elif type == 'poll':
            request_json['object']['type'] = 'Question'
            choices = [form.choice_1, form.choice_2, form.choice_3, form.choice_4, form.choice_5,
                       form.choice_6, form.choice_7, form.choice_8, form.choice_9, form.choice_10]
            key = 'oneOf' if form.mode.data == 'single' else 'anyOf'
            request_json['object'][key] = []
            for choice in choices:
                choice_data = choice.data.strip()
                if choice_data:
                    request_json['object'][key].append({'name': choice_data})
            request_json['object']['endTime'] = end_poll_date(form.finish_in.data)

        # todo: add try..except
        post = Post.new(current_user, community, request_json)

        if form.notify_author.data:
            new_notification = NotificationSubscription(name=post.title, user_id=current_user.id, entity_id=post.id, type=NOTIF_POST)
            db.session.add(new_notification)
        current_user.language_id = form.language_id.data
        g.site.last_active = utcnow()
        post.ap_id = f"https://{current_app.config['SERVER_NAME']}/post/{post.id}"
        db.session.commit()

        upvote_own_post(post)

        if post.type == POST_TYPE_POLL:
            poll = Poll.query.filter_by(post_id=post.id).first()
            if not poll.local_only:
                federate_post_to_user_followers(post)
            if not community.local_only and not poll.local_only:
                federate_post(community, post)
        else:
            federate_post_to_user_followers(post)
            if not community.local_only:
                federate_post(community, post)

        return redirect(f"/post/{post.id}")
    else: # GET
        form.communities.data = community.id
        form.notify_author.data = True
        if post_type == POST_TYPE_POLL:
            form.finish_in.data = '3d'
        if community.posting_warning:
            flash(community.posting_warning)

        # The source query parameter is used when cross-posting - load the source post's content into the form
        if post_type == POST_TYPE_LINK and request.args.get('source'):
            source_post = Post.query.get(request.args.get('source'))
            if source_post.deleted:
                abort(404)
            form.title.data = source_post.title
            form.body.data = source_post.body
            form.nsfw.data = source_post.nsfw
            form.nsfl.data = source_post.nsfl
            form.language_id.data = source_post.language_id
            form.link_url.data = source_post.url

    
    # empty post to pass since add_post.html extends edit_post.html 
    # and that one checks for a post.image_id for editing image posts
    post = None

    return render_template('community/add_post.html', title=_('Add post to community'), form=form,
                           post_type=post_type, community=community, post=post,
                           markdown_editor=current_user.markdown_editor, low_bandwidth=False, actor=actor,
                           moderating_communities=moderating_communities(current_user.get_id()),
                           joined_communities=joined_communities(current_user.id),
                           menu_topics=menu_topics(), site=g.site,
                           inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
    )


def federate_post(community, post):
    page = {
        'type': 'Page',
        'id': post.ap_id,
        'attributedTo': current_user.public_url(),
        'to': [
            community.public_url(),
            'https://www.w3.org/ns/activitystreams#Public'
        ],
        'name': post.title,
        'cc': [],
        'content': post.body_html if post.body_html else '',
        'mediaType': 'text/html',
        'source': {'content': post.body if post.body else '', 'mediaType': 'text/markdown'},
        'attachment': [],
        'commentsEnabled': post.comments_enabled,
        'sensitive': post.nsfw,
        'nsfl': post.nsfl,
        'stickied': post.sticky,
        'published': ap_datetime(utcnow()),
        'audience': community.public_url(),
        'language': {
            'identifier': post.language_code(),
            'name': post.language_name()
        },
        'tag': post.tags_for_activitypub()
    }
    create = {
        "id": f"https://{current_app.config['SERVER_NAME']}/activities/create/{gibberish(15)}",
        "actor": current_user.public_url(),
        "to": [
            "https://www.w3.org/ns/activitystreams#Public"
        ],
        "cc": [
            community.public_url()
        ],
        "type": "Create",
        "audience": community.public_url(),
        "object": page,
        '@context': default_context()
    }
    if post.type == POST_TYPE_LINK or post.type == POST_TYPE_VIDEO:
        page['attachment'] = [{'href': post.url, 'type': 'Link'}]
    elif post.image_id:
        image_url = ''
        if post.image.source_url:
            image_url = post.image.source_url
        elif post.image.file_path:
            image_url = post.image.file_path.replace('app/static/',
                                                     f"https://{current_app.config['SERVER_NAME']}/static/")
        elif post.image.thumbnail_path:
            image_url = post.image.thumbnail_path.replace('app/static/',
                                                          f"https://{current_app.config['SERVER_NAME']}/static/")
        # NB image is a dict while attachment is a list of dicts (usually just one dict in the list)
        page['image'] = {'type': 'Image', 'url': image_url}
        if post.type == POST_TYPE_IMAGE:
            page['attachment'] = [{'type': 'Image',
                                   'url': post.image.source_url,  # source_url is always a https link, no need for .replace() as done above
                                   'name': post.image.alt_text}]

    if post.type == POST_TYPE_POLL:
        poll = Poll.query.filter_by(post_id=post.id).first()
        page['type'] = 'Question'
        page['endTime'] = ap_datetime(poll.end_poll)
        page['votersCount'] = 0
        choices = []
        for choice in PollChoice.query.filter_by(post_id=post.id).all():
            choices.append({
                "type": "Note",
                "name": choice.choice_text,
                "replies": {
                  "type": "Collection",
                  "totalItems": 0
                }
            })
        page['oneOf' if poll.mode == 'single' else 'anyOf'] = choices
    if not community.is_local():  # this is a remote community - send the post to the instance that hosts it
        post_request_in_background(community.ap_inbox_url, create, current_user.private_key,
                               current_user.public_url() + '#main-key', timeout=10)
        flash(_('Your post to %(name)s has been made.', name=community.title))
    else:  # local community - send (announce) post out to followers
        announce = {
            "id": f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}",
            "type": 'Announce',
            "to": [
                "https://www.w3.org/ns/activitystreams#Public"
            ],
            "actor": community.public_url(),
            "cc": [
                community.ap_followers_url
            ],
            '@context': default_context(),
            'object': create
        }
        microblog_announce = copy(announce)
        microblog_announce['object'] = post.ap_id

        sent_to = 0
        for instance in community.following_instances():
            if instance.inbox and not current_user.has_blocked_instance(instance.id) and not instance_banned(
                    instance.domain):
                if instance.software in MICROBLOG_APPS:
                    send_to_remote_instance(instance.id, community.id, microblog_announce)
                else:
                    send_to_remote_instance(instance.id, community.id, announce)
                sent_to += 1
        if sent_to:
            flash(_('Your post to %(name)s has been made.', name=community.title))
        else:
            flash(_('Your post to %(name)s has been made.', name=community.title))


def federate_post_to_user_followers(post):
    followers = UserFollower.query.filter_by(local_user_id=post.user_id)
    if not followers:
        return

    note = {
        'type': 'Note',
        'id': post.ap_id,
        'inReplyTo': None,
        'attributedTo': current_user.public_url(),
        'to': [
            'https://www.w3.org/ns/activitystreams#Public'
        ],
        'cc': [
            current_user.followers_url()
        ],
        'content': '',
        'mediaType': 'text/html',
        'attachment': [],
        'commentsEnabled': post.comments_enabled,
        'sensitive': post.nsfw,
        'nsfl': post.nsfl,
        'stickied': post.sticky,
        'published': ap_datetime(utcnow()),
        'language': {
            'identifier': post.language_code(),
            'name': post.language_name()
        },
        'tag': post.tags_for_activitypub()
    }
    create = {
        "id": f"https://{current_app.config['SERVER_NAME']}/activities/create/{gibberish(15)}",
        "actor": current_user.public_url(),
        "to": [
            "https://www.w3.org/ns/activitystreams#Public"
        ],
        "cc": [
            current_user.followers_url()
        ],
        "type": "Create",
        "object": note,
        '@context': default_context()
    }
    if post.type == POST_TYPE_ARTICLE:
        note['content'] = '<p>' + post.title + '</p>'
    elif post.type == POST_TYPE_LINK or post.type == POST_TYPE_VIDEO:
        note['content'] = '<p><a href=' + post.url + '>' + post.title + '</a></p>'
    elif post.type == POST_TYPE_IMAGE:
        note['content'] = '<p>' + post.title + '</p>'
        if post.image_id and post.image.source_url:
            note['attachment'] = [{'type': 'Image', 'url': post.image.source_url, 'name': post.image.alt_text}]

    if post.body_html:
        note['content'] = note['content'] + '<p>' + post.body_html + '</p>'

    if post.type == POST_TYPE_POLL:
        poll = Poll.query.filter_by(post_id=post.id).first()
        note['type'] = 'Question'
        note['endTime'] = ap_datetime(poll.end_poll)
        note['votersCount'] = 0
        choices = []
        for choice in PollChoice.query.filter_by(post_id=post.id).all():
            choices.append({
                "type": "Note",
                "name": choice.choice_text,
                "replies": {
                  "type": "Collection",
                  "totalItems": 0
                }
            })
        note['oneOf' if poll.mode == 'single' else 'anyOf'] = choices

    instances = Instance.query.join(User, User.instance_id == Instance.id).join(UserFollower, UserFollower.remote_user_id == User.id)
    instances = instances.filter(UserFollower.local_user_id == post.user_id).filter(Instance.gone_forever == False)
    for instance in instances:
        if instance.inbox and not current_user.has_blocked_instance(instance.id) and not instance_banned(instance.domain):
            post_request_in_background(instance.inbox, create, current_user.private_key, current_user.public_url() + '#main-key')


@bp.route('/community/<int:community_id>/report', methods=['GET', 'POST'])
@login_required
def community_report(community_id: int):
    community = Community.query.get_or_404(community_id)
    form = ReportCommunityForm()
    if form.validate_on_submit():
        report = Report(reasons=form.reasons_to_string(form.reasons.data), description=form.description.data,
                        type=1, reporter_id=current_user.id, suspect_community_id=community.id, source_instance_id=1)
        db.session.add(report)

        # Notify admin
        # todo: find all instance admin(s). for now just load User.id == 1
        admins = [User.query.get_or_404(1)]
        for admin in admins:
            notification = Notification(user_id=admin.id, title=_('A community has been reported'),
                                            url=community.local_url(),
                                            author_id=current_user.id)
            db.session.add(notification)
            admin.unread_notifications += 1
        db.session.commit()

        # todo: federate report to originating instance
        if not community.is_local() and form.report_remote.data:
            ...

        flash(_('Community has been reported, thank you!'))
        return redirect(community.local_url())

    return render_template('community/community_report.html', title=_('Report community'), form=form, community=community)


@bp.route('/community/<int:community_id>/edit', methods=['GET', 'POST'])
@login_required
def community_edit(community_id: int):
    from app.admin.util import topics_for_form
    if current_user.banned:
        return show_ban_message()
    community = Community.query.get_or_404(community_id)
    old_topic_id = community.topic_id if community.topic_id else None
    if community.is_owner() or current_user.is_admin():
        form = EditCommunityForm()
        form.topic.choices = topics_for_form(0)
        form.languages.choices = languages_for_form()
        if form.validate_on_submit():
            community.title = form.title.data
            community.description = piefed_markdown_to_lemmy_markdown(form.description.data)
            community.description_html = markdown_to_html(form.description.data, anchors_new_tab=False)
            community.rules = form.rules.data
            community.rules_html = markdown_to_html(form.rules.data, anchors_new_tab=False)
            community.nsfw = form.nsfw.data
            community.local_only = form.local_only.data
            community.restricted_to_mods = form.restricted_to_mods.data
            community.new_mods_wanted = form.new_mods_wanted.data
            community.topic_id = form.topic.data if form.topic.data != 0 else None
            community.default_layout = form.default_layout.data

            icon_file = request.files['icon_file']
            if icon_file and icon_file.filename != '':
                if community.icon_id:
                    community.icon.delete_from_disk()
                file = save_icon_file(icon_file)
                if file:
                    community.icon = file
                    cache.delete_memoized(Community.icon_image, community)
            banner_file = request.files['banner_file']
            if banner_file and banner_file.filename != '':
                if community.image_id:
                    community.image.delete_from_disk()
                file = save_banner_file(banner_file)
                if file:
                    community.image = file
                    cache.delete_memoized(Community.header_image, community)

            # Languages of the community
            db.session.execute(text('DELETE FROM "community_language" WHERE community_id = :community_id'),
                               {'community_id': community_id})
            for language_choice in form.languages.data:
                community.languages.append(Language.query.get(language_choice))
            # Always include the undetermined language, so posts with no language will be accepted
            community.languages.append(Language.query.filter(Language.code == 'und').first())
            db.session.commit()

            if community.topic_id != old_topic_id:
                if community.topic_id:
                    community.topic.num_communities = community.topic.communities.count()
                if old_topic_id:
                    topic = Topic.query.get(old_topic_id)
                    if topic:
                        topic.num_communities = topic.communities.count()
                db.session.commit()
            flash(_('Saved'))
            return redirect(url_for('activitypub.community_profile', actor=community.ap_id if community.ap_id is not None else community.name))
        else:
            form.title.data = community.title
            form.description.data = community.description
            form.rules.data = community.rules
            form.nsfw.data = community.nsfw
            form.local_only.data = community.local_only
            form.new_mods_wanted.data = community.new_mods_wanted
            form.restricted_to_mods.data = community.restricted_to_mods
            form.topic.data = community.topic_id if community.topic_id else None
            form.languages.data = community.language_ids()
            form.default_layout.data = community.default_layout
        return render_template('community/community_edit.html', title=_('Edit community'), form=form,
                               current_app=current_app, current="edit_settings",
                               community=community, moderating_communities=moderating_communities(current_user.get_id()),
                               joined_communities=joined_communities(current_user.get_id()),
                               menu_topics=menu_topics(), site=g.site)
    else:
        abort(401)


@bp.route('/community/<int:community_id>/remove_icon', methods=['GET', 'POST'])
@login_required
def remove_icon(community_id):
    community = Community.query.get_or_404(community_id)
    if community.icon_id:
        community.icon.delete_from_disk()
        if community.icon_id:
            file = File.query.get(community.icon_id)
            file.delete_from_disk()
            community.icon_id = None
            db.session.delete(file)
            db.session.commit()
            cache.delete_memoized(Community.icon_image, community)
    return _('Icon removed!')


@bp.route('/community/<int:community_id>/remove_header', methods=['GET', 'POST'])
@login_required
def remove_header(community_id):
    community = Community.query.get_or_404(community_id)
    if community.image_id:
        community.image.delete_from_disk()
        if community.image_id:
            file = File.query.get(community.image_id)
            file.delete_from_disk()
            community.image_id = None
            db.session.delete(file)
            db.session.commit()
            cache.delete_memoized(Community.header_image, community)
    return '<div> ' + _('Banner removed!') + '</div>'


@bp.route('/community/<int:community_id>/delete', methods=['GET', 'POST'])
@login_required
def community_delete(community_id: int):
    if current_user.banned:
        return show_ban_message()
    community = Community.query.get_or_404(community_id)
    if community.is_owner() or current_user.is_admin():
        form = DeleteCommunityForm()
        if form.validate_on_submit():
            if community.is_local():
                community.banned = True
                # todo: federate deletion out to all instances. At end of federation process, delete_dependencies() and delete community

            # record for modlog
            reason = f"Community {community.name} deleted by {current_user.user_name}"
            add_to_modlog('delete_community', reason=reason)

            # actually delete the community
            community.delete_dependencies()
            db.session.delete(community)
            db.session.commit()

            flash(_('Community deleted'))
            return redirect('/communities')

        return render_template('community/community_delete.html', title=_('Delete community'), form=form,
                               community=community, moderating_communities=moderating_communities(current_user.get_id()),
                               joined_communities=joined_communities(current_user.get_id()),
                               menu_topics=menu_topics(), site=g.site)
    else:
        abort(401)


@bp.route('/community/<int:community_id>/moderators', methods=['GET', 'POST'])
@login_required
def community_mod_list(community_id: int):
    if current_user.banned:
        return show_ban_message()
    community = Community.query.get_or_404(community_id)
    if community.is_owner() or current_user.is_admin() or community.is_moderator(current_user):

        moderators = User.query.filter(User.banned == False).join(CommunityMember, CommunityMember.user_id == User.id).\
            filter(CommunityMember.community_id == community_id, or_(CommunityMember.is_moderator == True, CommunityMember.is_owner == True)).all()

        return render_template('community/community_mod_list.html', title=_('Moderators for %(community)s', community=community.display_name()),
                        moderators=moderators, community=community, current="moderators",
                        moderating_communities=moderating_communities(current_user.get_id()),
                        joined_communities=joined_communities(current_user.get_id()),
                        menu_topics=menu_topics(), site=g.site
                        )
    else:
        abort(401)


@bp.route('/community/<int:community_id>/moderators/add/<int:user_id>', methods=['GET', 'POST'])
@login_required
def community_add_moderator(community_id: int, user_id: int):
    if current_user.banned:
        return show_ban_message()
    community = Community.query.get_or_404(community_id)
    new_moderator = User.query.get_or_404(user_id)
    if community.is_owner() or current_user.is_admin() and not new_moderator.banned:
        existing_member = CommunityMember.query.filter(CommunityMember.user_id == new_moderator.id,
                                                       CommunityMember.community_id == community_id).first()
        if existing_member:
            existing_member.is_moderator = True
        else:
            new_member = CommunityMember(community_id=community_id, user_id=new_moderator.id, is_moderator=True)
            db.session.add(new_member)
        db.session.commit()
        flash(_('Moderator added'))

        # Notify new mod
        if new_moderator.is_local():
            notify = Notification(title=_('You are now a moderator of %(name)s', name=community.display_name()),
                                  url='/c/' + community.name, user_id=new_moderator.id,
                                  author_id=current_user.id)
            new_moderator.unread_notifications += 1
            db.session.add(notify)
            db.session.commit()
        else:
            # for remote users, send a chat message to let them know
            existing_conversation = Conversation.find_existing_conversation(recipient=new_moderator,
                                                                            sender=current_user)
            if not existing_conversation:
                existing_conversation = Conversation(user_id=current_user.id)
                existing_conversation.members.append(new_moderator)
                existing_conversation.members.append(current_user)
                db.session.add(existing_conversation)
                db.session.commit()
            server = current_app.config['SERVER_NAME']
            send_message(f"Hi there. I've added you as a moderator to the community !{community.name}@{server}.",
                         existing_conversation.id)

        add_to_modlog('add_mod', community_id=community_id, link_text=new_moderator.display_name(),
                      link=new_moderator.link())

        # Flush cache
        cache.delete_memoized(moderating_communities, new_moderator.id)
        cache.delete_memoized(joined_communities, new_moderator.id)
        cache.delete_memoized(community_moderators, community_id)
        return redirect(url_for('community.community_mod_list', community_id=community.id))


@bp.route('/community/<int:community_id>/moderators/find', methods=['GET', 'POST'])
@login_required
def community_find_moderator(community_id: int):
    if current_user.banned:
        return show_ban_message()
    community = Community.query.get_or_404(community_id)
    if community.is_owner() or current_user.is_admin():
        form = AddModeratorForm()
        potential_moderators = None
        if form.validate_on_submit():
            potential_moderators = find_local_users(form.user_name.data)

        return render_template('community/community_find_moderator.html', title=_('Add moderator to %(community)s',
                                                                                 community=community.display_name()),
                               community=community, form=form, potential_moderators=potential_moderators,
                               moderating_communities=moderating_communities(current_user.get_id()),
                               joined_communities=joined_communities(current_user.get_id()),
                               menu_topics=menu_topics(), site=g.site
                               )
    else:
        abort(401)


@bp.route('/community/<int:community_id>/moderators/remove/<int:user_id>', methods=['GET', 'POST'])
@login_required
def community_remove_moderator(community_id: int, user_id: int):
    if current_user.banned:
        return show_ban_message()
    community = Community.query.get_or_404(community_id)
    if community.is_owner() or current_user.is_admin() or user_id == current_user.id:

        existing_member = CommunityMember.query.filter(CommunityMember.user_id == user_id,
                                                       CommunityMember.community_id == community_id).first()
        if existing_member:
            existing_member.is_moderator = False
            db.session.commit()
            flash(_('Moderator removed'))

            removed_mod = User.query.get(existing_member.user_id)

            add_to_modlog('remove_mod', community_id=community_id, link_text=removed_mod.display_name(),
                          link=removed_mod.link())

            # Flush cache
            cache.delete_memoized(moderating_communities, user_id)
            cache.delete_memoized(joined_communities, user_id)
            cache.delete_memoized(community_moderators, community_id)

        return redirect(url_for('community.community_mod_list', community_id=community.id))
    else:
        abort(401)


@bp.route('/community/<int:community_id>/block_instance', methods=['GET', 'POST'])
@login_required
def community_block_instance(community_id: int):
    community = Community.query.get_or_404(community_id)
    existing = InstanceBlock.query.filter_by(user_id=current_user.id, instance_id=community.instance_id).first()
    if not existing:
        db.session.add(InstanceBlock(user_id=current_user.id, instance_id=community.instance_id))
        db.session.commit()
    flash(_('Content from %(name)s will be hidden.', name=community.instance.domain))
    return redirect(community.local_url())


@bp.route('/community/<int:community_id>/<int:user_id>/ban_user_community', methods=['GET', 'POST'])
@login_required
def community_ban_user(community_id: int, user_id: int):
    community = Community.query.get_or_404(community_id)
    user = User.query.get_or_404(user_id)
    existing = CommunityBan.query.filter_by(community_id=community.id, user_id=user.id).first()

    form = BanUserCommunityForm()
    if form.validate_on_submit():
        # Both CommunityBan and CommunityMember need to be updated. CommunityBan is under the control of moderators while
        # CommunityMember can be cleared by the user by leaving the group and rejoining. CommunityMember.is_banned stops
        # posts from the community from showing up in the banned person's home feed.
        if not existing:
            new_ban = CommunityBan(community_id=community_id, user_id=user.id, banned_by=current_user.id,
                                   reason=form.reason.data)
            if form.ban_until.data is not None and form.ban_until.data > utcnow().date():
                new_ban.ban_until = form.ban_until.data
            db.session.add(new_ban)
            db.session.commit()

        community_membership_record = CommunityMember.query.filter_by(community_id=community.id, user_id=user.id).first()
        if community_membership_record:
            community_membership_record.is_banned = True
            db.session.commit()

        flash(_('%(name)s has been banned.', name=user.display_name()))

        if form.delete_posts.data:
            posts = Post.query.filter(Post.user_id == user.id, Post.community_id == community.id).all()
            for post in posts:
                delete_post_from_community(post.id)
            if posts:
                flash(_('Posts by %(name)s have been deleted.', name=user.display_name()))
        if form.delete_post_replies.data:
            post_replies = PostReply.query.filter(PostReply.user_id == user.id, Post.community_id == community.id).all()
            for post_reply in post_replies:
                delete_post_reply_from_community(post_reply.id)
            if post_replies:
                flash(_('Comments by %(name)s have been deleted.', name=user.display_name()))

        # todo: federate ban to post author instance

        # Notify banned person
        if user.is_local():
            cache.delete_memoized(communities_banned_from, user.id)
            cache.delete_memoized(joined_communities, user.id)
            cache.delete_memoized(moderating_communities, user.id)
            notify = Notification(title=shorten_string('You have been banned from ' + community.title),
                                  url=f'/notifications', user_id=user.id,
                                  author_id=1)
            db.session.add(notify)
            user.unread_notifications += 1
            db.session.commit()
        else:
            ...
            # todo: send chatmessage to remote user and federate it

        # Remove their notification subscription,  if any
        db.session.query(NotificationSubscription).filter(NotificationSubscription.entity_id == community.id,
                                                          NotificationSubscription.user_id == user.id,
                                                          NotificationSubscription.type == NOTIF_COMMUNITY).delete()

        add_to_modlog('ban_user', community_id=community.id, link_text=user.display_name(), link=user.link())

        return redirect(community.local_url())
    else:
        return render_template('community/community_ban_user.html', title=_('Ban from community'), form=form, community=community,
                               user=user,
                               moderating_communities=moderating_communities(current_user.get_id()),
                               joined_communities=joined_communities(current_user.get_id()),
                               menu_topics=menu_topics(), site=g.site,
                               inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                               )


@bp.route('/community/<int:community_id>/<int:user_id>/unban_user_community', methods=['GET', 'POST'])
@login_required
def community_unban_user(community_id: int, user_id: int):
    community = Community.query.get_or_404(community_id)
    user = User.query.get_or_404(user_id)
    existing_ban = CommunityBan.query.filter_by(community_id=community.id, user_id=user.id).first()
    if existing_ban:
        db.session.delete(existing_ban)
        db.session.commit()

    community_membership_record = CommunityMember.query.filter_by(community_id=community.id, user_id=user.id).first()
    if community_membership_record:
        community_membership_record.is_banned = False
        db.session.commit()

    flash(_('%(name)s has been unbanned.', name=user.display_name()))

    # todo: federate ban to post author instance

    # notify banned person
    if user.is_local():
        cache.delete_memoized(communities_banned_from, user.id)
        cache.delete_memoized(joined_communities, user.id)
        cache.delete_memoized(moderating_communities, user.id)
        notify = Notification(title=shorten_string('You have been un-banned from ' + community.title),
                              url=f'/notifications', user_id=user.id,
                              author_id=1)
        db.session.add(notify)
        user.unread_notifications += 1
        db.session.commit()
    else:
        ...
        # todo: send chatmessage to remote user and federate it

    add_to_modlog('unban_user', community_id=community.id, link_text=user.display_name(), link=user.link())

    return redirect(url_for('community.community_moderate_subscribers', actor=community.link()))


@bp.route('/<int:community_id>/notification', methods=['GET', 'POST'])
@login_required
def community_notification(community_id: int):
    # Toggle whether the current user is subscribed to notifications about this community's posts or not
    community = Community.query.get_or_404(community_id)
    existing_notification = NotificationSubscription.query.filter(NotificationSubscription.entity_id == community.id,
                                                                  NotificationSubscription.user_id == current_user.id,
                                                                  NotificationSubscription.type == NOTIF_COMMUNITY).first()
    if existing_notification:
        db.session.delete(existing_notification)
        db.session.commit()
    else:  # no subscription yet, so make one
        if community.id not in communities_banned_from(current_user.id):
            new_notification = NotificationSubscription(name=shorten_string(_('New posts in %(community_name)s', community_name=community.title)),
                                                        user_id=current_user.id, entity_id=community.id,
                                                        type=NOTIF_COMMUNITY)
            db.session.add(new_notification)
            db.session.commit()

    member_info = CommunityMember.query.filter(CommunityMember.community_id == community.id,
                                               CommunityMember.user_id == current_user.id).first()
    # existing community members get their notification flag toggled
    if member_info and not member_info.is_banned:
        member_info.notify_new_posts = not member_info.notify_new_posts
        db.session.commit()
    else:   # people who are not yet members become members, with notify on.
        if community.id not in communities_banned_from(current_user.id):
            new_member = CommunityMember(community_id=community.id, user_id=current_user.id, notify_new_posts=True)
            db.session.add(new_member)
            db.session.commit()

    return render_template('community/_notification_toggle.html', community=community)


@bp.route('/<actor>/moderate', methods=['GET'])
@login_required
def community_moderate(actor):
    if current_user.banned:
        return show_ban_message()
    community = actor_to_community(actor)

    if community is not None:
        if community.is_moderator() or current_user.is_admin():

            page = request.args.get('page', 1, type=int)
            search = request.args.get('search', '')
            local_remote = request.args.get('local_remote', '')

            reports = Report.query.filter_by(status=0, in_community_id=community.id)
            if local_remote == 'local':
                reports = reports.filter(Report.source_instance_id == 1)
            if local_remote == 'remote':
                reports = reports.filter(Report.source_instance_id != 1)
            reports = reports.filter(Report.status >= 0).order_by(desc(Report.created_at)).paginate(page=page, per_page=1000, error_out=False)

            next_url = url_for('community.community_moderate', page=reports.next_num) if reports.has_next else None
            prev_url = url_for('community.community_moderate', page=reports.prev_num) if reports.has_prev and page != 1 else None

            return render_template('community/community_moderate.html', title=_('Moderation of %(community)s', community=community.display_name()),
                                   community=community, reports=reports, current='reports',
                                   next_url=next_url, prev_url=prev_url,
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )
        else:
            abort(401)
    else:
        abort(404)


@bp.route('/<actor>/moderate/subscribers', methods=['GET'])
@login_required
def community_moderate_subscribers(actor):
    community = actor_to_community(actor)

    if community is not None:
        if community.is_moderator() or current_user.is_admin():

            page = request.args.get('page', 1, type=int)
            low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'

            subscribers = User.query.join(CommunityMember, CommunityMember.user_id == User.id).filter(CommunityMember.community_id == community.id)
            subscribers = subscribers.filter(CommunityMember.is_banned == False)

            # Pagination
            subscribers = subscribers.paginate(page=page, per_page=100 if not low_bandwidth else 50, error_out=False)
            next_url = url_for('community.community_moderate_subscribers', actor=actor, page=subscribers.next_num) if subscribers.has_next else None
            prev_url = url_for('community.community_moderate_subscribers', actor=actor, page=subscribers.prev_num) if subscribers.has_prev and page != 1 else None

            banned_people = User.query.join(CommunityBan, CommunityBan.user_id == User.id).filter(CommunityBan.community_id == community.id).all()

            return render_template('community/community_moderate_subscribers.html', title=_('Moderation of %(community)s', community=community.display_name()),
                                   community=community, current='subscribers', subscribers=subscribers, banned_people=banned_people,
                                   next_url=next_url, prev_url=prev_url, low_bandwidth=low_bandwidth,
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )
        else:
            abort(401)
    else:
        abort(404)


@bp.route('/community/<int:community_id>/<int:user_id>/kick_user_community', methods=['GET', 'POST'])
@login_required
def community_kick_user(community_id: int, user_id: int):
    community = Community.query.get_or_404(community_id)
    user = User.query.get_or_404(user_id)

    if community is not None:
        if current_user.is_admin():

            db.session.query(CommunityMember).filter_by(user_id=user_id, community_id=community.id).delete()
            db.session.commit()

        else:
            abort(401)
    else:
        abort(404)

    return redirect(url_for('community.community_moderate_subscribers', actor=community.name))


@bp.route('/<actor>/moderate/wiki', methods=['GET'])
@login_required
def community_wiki_list(actor):
    community = actor_to_community(actor)

    if community is not None:
        if community.is_moderator() or current_user.is_admin():
            low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'
            pages = CommunityWikiPage.query.filter(CommunityWikiPage.community_id == community.id).order_by(CommunityWikiPage.title).all()
            return render_template('community/community_wiki_list.html', title=_('Community Wiki'), community=community,
                                   pages=pages, low_bandwidth=low_bandwidth, current='wiki',
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )
        else:
            abort(401)
    else:
        abort(404)


@bp.route('/<actor>/moderate/wiki/add', methods=['GET', 'POST'])
@login_required
def community_wiki_add(actor):
    community = actor_to_community(actor)

    if community is not None:
        if community.is_moderator() or current_user.is_admin():
            low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'
            form = EditCommunityWikiPageForm()
            if form.validate_on_submit():
                new_page = CommunityWikiPage(community_id=community.id, slug=form.slug.data, title=form.title.data,
                                             body=form.body.data, who_can_edit=form.who_can_edit.data)
                new_page.body_html = markdown_to_html(new_page.body)
                db.session.add(new_page)
                db.session.commit()

                initial_revision = CommunityWikiPageRevision(wiki_page_id=new_page.id, user_id=current_user.id,
                                                             community_id=community.id, title=form.title.data,
                                                             body=form.body.data, body_html=new_page.body_html)
                db.session.add(initial_revision)
                db.session.commit()

                flash(_('Saved'))
                return redirect(url_for('community.community_wiki_list', actor=community.link()))

            return render_template('community/community_wiki_edit.html', title=_('Add wiki page'), community=community,
                                   form=form, low_bandwidth=low_bandwidth, current='wiki',
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )
        else:
            abort(401)
    else:
        abort(404)


@bp.route('/<actor>/wiki/<slug>', methods=['GET', 'POST'])
def community_wiki_view(actor, slug):
    community = actor_to_community(actor)

    if community is not None:
        page: CommunityWikiPage = CommunityWikiPage.query.filter_by(slug=slug, community_id=community.id).first()
        if page is None:
            abort(404)
        else:
            # Breadcrumbs
            breadcrumbs = []
            breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
            breadcrumb.text = _('Home')
            breadcrumb.url = '/'
            breadcrumbs.append(breadcrumb)

            if community.topic_id:
                topics = []
                previous_topic = Topic.query.get(community.topic_id)
                topics.append(previous_topic)
                while previous_topic.parent_id:
                    topic = Topic.query.get(previous_topic.parent_id)
                    topics.append(topic)
                    previous_topic = topic
                topics = list(reversed(topics))

                breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
                breadcrumb.text = _('Topics')
                breadcrumb.url = '/topics'
                breadcrumbs.append(breadcrumb)

                existing_url = '/topic'
                for topic in topics:
                    breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
                    breadcrumb.text = topic.name
                    breadcrumb.url = f"{existing_url}/{topic.machine_name}"
                    breadcrumbs.append(breadcrumb)
                    existing_url = breadcrumb.url
            else:
                breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
                breadcrumb.text = _('Communities')
                breadcrumb.url = '/communities'
                breadcrumbs.append(breadcrumb)

            return render_template('community/community_wiki_page_view.html', title=page.title, page=page,
                                   community=community, breadcrumbs=breadcrumbs, is_moderator=community.is_moderator(),
                                   is_owner=community.is_owner(),
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[
                                       randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )


@bp.route('/<actor>/wiki/<slug>/<revision_id>', methods=['GET', 'POST'])
@login_required
def community_wiki_view_revision(actor, slug, revision_id):
    community = actor_to_community(actor)

    if community is not None:
        page: CommunityWikiPage = CommunityWikiPage.query.filter_by(slug=slug, community_id=community.id).first()
        revision: CommunityWikiPageRevision = CommunityWikiPageRevision.query.get_or_404(revision_id)
        if page is None or revision is None:
            abort(404)
        else:
            # Breadcrumbs
            breadcrumbs = []
            breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
            breadcrumb.text = _('Home')
            breadcrumb.url = '/'
            breadcrumbs.append(breadcrumb)

            if community.topic_id:
                topics = []
                previous_topic = Topic.query.get(community.topic_id)
                topics.append(previous_topic)
                while previous_topic.parent_id:
                    topic = Topic.query.get(previous_topic.parent_id)
                    topics.append(topic)
                    previous_topic = topic
                topics = list(reversed(topics))

                breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
                breadcrumb.text = _('Topics')
                breadcrumb.url = '/topics'
                breadcrumbs.append(breadcrumb)

                existing_url = '/topic'
                for topic in topics:
                    breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
                    breadcrumb.text = topic.name
                    breadcrumb.url = f"{existing_url}/{topic.machine_name}"
                    breadcrumbs.append(breadcrumb)
                    existing_url = breadcrumb.url
            else:
                breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
                breadcrumb.text = _('Communities')
                breadcrumb.url = '/communities'
                breadcrumbs.append(breadcrumb)

            return render_template('community/community_wiki_revision_view.html', title=page.title, page=page,
                                   community=community, breadcrumbs=breadcrumbs, is_moderator=community.is_moderator(),
                                   is_owner=community.is_owner(), revision=revision,
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[
                                       randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )


@bp.route('/<actor>/wiki/<slug>/<revision_id>/revert', methods=['GET'])
@login_required
def community_wiki_revert_revision(actor, slug, revision_id):
    community = actor_to_community(actor)

    if community is not None:
        page: CommunityWikiPage = CommunityWikiPage.query.filter_by(slug=slug, community_id=community.id).first()
        revision: CommunityWikiPageRevision = CommunityWikiPageRevision.query.get_or_404(revision_id)
        if page is None or revision is None:
            abort(404)
        else:
            if page.can_edit(current_user, community):
                page.body = revision.body
                page.body_html = revision.body_html
                page.edited_at = utcnow()

                new_revision = CommunityWikiPageRevision(wiki_page_id=page.id, user_id=current_user.id,
                                                         community_id=community.id, title=revision.title,
                                                         body=revision.body, body_html=revision.body_html)
                db.session.add(new_revision)
                db.session.commit()

                flash(_('Reverted to old version of the page.'))
                return redirect(url_for('community.community_wiki_revisions', actor=community.link(), page_id=page.id))
            else:
                abort(401)


@bp.route('/<actor>/moderate/wiki/<int:page_id>/edit', methods=['GET', 'POST'])
@login_required
def community_wiki_edit(actor, page_id):
    community = actor_to_community(actor)

    if community is not None:
        page: CommunityWikiPage = CommunityWikiPage.query.get_or_404(page_id)
        if page.can_edit(current_user, community):
            low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'

            form = EditCommunityWikiPageForm()
            if form.validate_on_submit():
                page.title = form.title.data
                page.slug = form.slug.data
                page.body = form.body.data
                page.body_html = markdown_to_html(page.body)
                page.who_can_edit = form.who_can_edit.data
                page.edited_at = utcnow()
                new_revision = CommunityWikiPageRevision(wiki_page_id=page.id, user_id=current_user.id,
                                                             community_id=community.id, title=form.title.data,
                                                             body=form.body.data, body_html=page.body_html)
                db.session.add(new_revision)
                db.session.commit()
                flash(_('Saved'))
                if request.args.get('return') == 'list':
                    return redirect(url_for('community.community_wiki_list', actor=community.link()))
                elif request.args.get('return') == 'page':
                    return redirect(url_for('community.community_wiki_view', actor=community.link(), slug=page.slug))
            else:
                form.title.data = page.title
                form.slug.data = page.slug
                form.body.data = page.body
                form.who_can_edit.data = page.who_can_edit

            return render_template('community/community_wiki_edit.html', title=_('Edit wiki page'), community=community,
                                   form=form, low_bandwidth=low_bandwidth,
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )
        else:
            abort(401)
    else:
        abort(404)


@bp.route('/<actor>/moderate/wiki/<int:page_id>/revisions', methods=['GET', 'POST'])
@login_required
def community_wiki_revisions(actor, page_id):
    community = actor_to_community(actor)

    if community is not None:
        page: CommunityWikiPage = CommunityWikiPage.query.get_or_404(page_id)
        if page.can_edit(current_user, community):
            low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'

            revisions = CommunityWikiPageRevision.query.filter_by(wiki_page_id=page.id).\
                order_by(desc(CommunityWikiPageRevision.edited_at)).all()

            most_recent_revision = revisions[0].id

            return render_template('community/community_wiki_revisions.html', title=_('%(title)s revisions', title=page.title),
                                   community=community, page=page, revisions=revisions, most_recent_revision=most_recent_revision,
                                   low_bandwidth=low_bandwidth,
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )
        else:
            abort(401)
    else:
        abort(404)


@bp.route('/<actor>/moderate/wiki/<int:page_id>/delete', methods=['GET'])
@login_required
def community_wiki_delete(actor, page_id):
    community = actor_to_community(actor)

    if community is not None:
        page: CommunityWikiPage = CommunityWikiPage.query.get_or_404(page_id)
        if page.can_edit(current_user, community):
            db.session.delete(page)
            db.session.commit()
            flash(_('Page deleted'))
        return redirect(url_for('community.community_wiki_list', actor=community.link()))
    else:
        abort(404)


@bp.route('/<actor>/moderate/modlog', methods=['GET'])
@login_required
def community_modlog(actor):
    community = actor_to_community(actor)

    if community is not None:
        if community.is_moderator() or current_user.is_admin():

            page = request.args.get('page', 1, type=int)
            low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'

            modlog_entries = ModLog.query.filter(ModLog.community_id == community.id).order_by(desc(ModLog.created_at))

            # Pagination
            modlog_entries = modlog_entries.paginate(page=page, per_page=100 if not low_bandwidth else 50, error_out=False)
            next_url = url_for('community.community_modlog', actor=actor,
                               page=modlog_entries.next_num) if modlog_entries.has_next else None
            prev_url = url_for('community.community_modlog', actor=actor,
                               page=modlog_entries.prev_num) if modlog_entries.has_prev and page != 1 else None

            return render_template('community/community_modlog.html',
                                   title=_('Mod Log of %(community)s', community=community.display_name()),
                                   community=community, current='modlog', modlog_entries=modlog_entries,
                                   next_url=next_url, prev_url=prev_url, low_bandwidth=low_bandwidth,
                                   moderating_communities=moderating_communities(current_user.get_id()),
                                   joined_communities=joined_communities(current_user.get_id()),
                                   menu_topics=menu_topics(), site=g.site,
                                   inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None
                                   )

        else:
            abort(401)
    else:
        abort(404)


@bp.route('/community/<int:community_id>/moderate_report/<int:report_id>/escalate', methods=['GET', 'POST'])
@login_required
def community_moderate_report_escalate(community_id, report_id):
    community = Community.query.get_or_404(community_id)
    if community.is_moderator() or current_user.is_admin():
        report = Report.query.filter_by(in_community_id=community.id, id=report_id, status=REPORT_STATE_NEW).first()
        if report:
            form = EscalateReportForm()
            if form.validate_on_submit():
                notify = Notification(title='Escalated report', url='/admin/reports', user_id=1,
                                      author_id=current_user.id)
                db.session.add(notify)
                report.description = form.reason.data
                report.status = REPORT_STATE_ESCALATED
                db.session.commit()
                flash(_('Admin has been notified about this report.'))
                # todo: remove unread notifications about this report
                # todo: append to mod log
                return redirect(url_for('community.community_moderate', actor=community.link()))
            else:
                form.reason.data = report.description
                return render_template('community/community_moderate_report_escalate.html', form=form)
    else:
        abort(401)


@bp.route('/community/<int:community_id>/moderate_report/<int:report_id>/resolve', methods=['GET', 'POST'])
@login_required
def community_moderate_report_resolve(community_id, report_id):
    community = Community.query.get_or_404(community_id)
    if community.is_moderator() or current_user.is_admin():
        report = Report.query.filter_by(in_community_id=community.id, id=report_id).first()
        if report:
            form = ResolveReportForm()
            if form.validate_on_submit():
                report.status = REPORT_STATE_RESOLVED

                # Reset the 'reports' counter on the comment, post or user
                if report.suspect_post_reply_id:
                    post_reply = PostReply.query.get(report.suspect_post_reply_id)
                    post_reply.reports = 0
                elif report.suspect_post_id:
                    post = Post.query.get(report.suspect_post_id)
                    post.reports = 0
                elif report.suspect_user_id:
                    user = User.query.get(report.suspect_user_id)
                    user.reports = 0
                db.session.commit()

                # todo: remove unread notifications about this report
                # todo: append to mod log
                if form.also_resolve_others.data:
                    if report.suspect_post_reply_id:
                        db.session.execute(text('UPDATE "report" SET status = :new_status WHERE suspect_post_reply_id = :suspect_post_reply_id'),
                                           {'new_status': REPORT_STATE_RESOLVED,
                                            'suspect_post_reply_id': report.suspect_post_reply_id})
                        # todo: remove unread notifications about these reports
                    elif report.suspect_post_id:
                        db.session.execute(text('UPDATE "report" SET status = :new_status WHERE suspect_post_id = :suspect_post_id'),
                                           {'new_status': REPORT_STATE_RESOLVED,
                                            'suspect_post_id': report.suspect_post_id})
                        # todo: remove unread notifications about these reports
                    db.session.commit()
                flash(_('Report resolved.'))
                return redirect(url_for('community.community_moderate', actor=community.link()))
            else:
                return render_template('community/community_moderate_report_resolve.html', form=form)


@bp.route('/community/<int:community_id>/moderate_report/<int:report_id>/ignore', methods=['GET', 'POST'])
@login_required
def community_moderate_report_ignore(community_id, report_id):
    community = Community.query.get_or_404(community_id)
    if community.is_moderator() or current_user.is_admin():
        report = Report.query.filter_by(in_community_id=community.id, id=report_id).first()
        if report:
            # Set the 'reports' counter on the comment, post or user to -1 to ignore all future reports
            if report.suspect_post_reply_id:
                post_reply = PostReply.query.get(report.suspect_post_reply_id)
                post_reply.reports = -1
            elif report.suspect_post_id:
                post = Post.query.get(report.suspect_post_id)
                post.reports = -1
            elif report.suspect_user_id:
                user = User.query.get(report.suspect_user_id)
                user.reports = -1
            db.session.commit()

            # todo: append to mod log

            if report.suspect_post_reply_id:
                db.session.execute(text('UPDATE "report" SET status = :new_status WHERE suspect_post_reply_id = :suspect_post_reply_id'),
                                   {'new_status': REPORT_STATE_DISCARDED,
                                    'suspect_post_reply_id': report.suspect_post_reply_id})
                # todo: remove unread notifications about these reports
            elif report.suspect_post_id:
                db.session.execute(text('UPDATE "report" SET status = :new_status WHERE suspect_post_id = :suspect_post_id'),
                                   {'new_status': REPORT_STATE_DISCARDED,
                                    'suspect_post_id': report.suspect_post_id})
                # todo: remove unread notifications about these reports
            db.session.commit()
            flash(_('Report ignored.'))
            return redirect(url_for('community.community_moderate', actor=community.link()))
        else:
            abort(404)


@bp.route('/lookup/<community>/<domain>')
def lookup(community, domain):
    if domain == current_app.config['SERVER_NAME']:
        return redirect('/c/' + community)

    exists = Community.query.filter_by(name=community, ap_domain=domain).first()
    if exists:
        return redirect('/c/' + community + '@' + domain)
    else:
        address = '!' + community + '@' + domain
        if current_user.is_authenticated:
            new_community = None

            try:
                new_community = search_for_community(address)
            except Exception as e:
                if 'is blocked.' in str(e):
                    flash(_('Sorry, that instance is blocked, check https://gui.fediseer.com/ for reasons.'), 'warning')
            if new_community is None:
                if g.site.enable_nsfw:
                    flash(_('Community not found.'), 'warning')
                else:
                    flash(_('Community not found. If you are searching for a nsfw community it is blocked by this instance.'), 'warning')
            else:
                if new_community.banned:
                    flash(_('That community is banned from %(site)s.', site=g.site.name), 'warning')

            return render_template('community/lookup_remote.html',
                           title=_('Search result for remote community'), new_community=new_community,
                           subscribed=community_membership(current_user, new_community) >= SUBSCRIPTION_MEMBER)
        else:
            # send them back where they came from
            flash('Searching for remote communities requires login', 'error')
            referrer = request.headers.get('Referer', None)
            if referrer is not None:
                return redirect(referrer)
            else:
                return redirect('/')


@bp.route('/check_url_already_posted')
def check_url_already_posted():
    url = request.args.get('link_url')
    if url:
        url = remove_tracking_from_link(url.strip())
        communities = Community.query.filter_by(banned=False).join(Post).filter(Post.url == url, Post.deleted == False).all()
        return flask.render_template('community/check_url_posted.html', communities=communities)
    else:
        abort(404)


def upvote_own_post(post):
        post.score = 1
        post.up_votes = 1
        post.ranking = post.post_ranking(post.score, utcnow())
        vote = PostVote(user_id=current_user.id, post_id=post.id, author_id=current_user.id, effect=1)
        db.session.add(vote)
        db.session.commit()
        cache.delete_memoized(recently_upvoted_posts, current_user.id)
