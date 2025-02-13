# ----- imports -----
import flask
from datetime import timedelta
from random import randint
from typing import List
from flask import g, current_app, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from flask_babel import _
from app import db, cache, celery
from app.activitypub.signature import RsaKeys, post_request
from app.activitypub.util import find_actor_or_create
from app.community.util import save_icon_file, save_banner_file
from app.constants import SUBSCRIPTION_OWNER, SUBSCRIPTION_MODERATOR, POST_TYPE_IMAGE, \
    POST_TYPE_LINK, POST_TYPE_VIDEO, NOTIF_FEED, SUBSCRIPTION_MEMBER, SUBSCRIPTION_PENDING
from app.feed import  bp
from app.feed.forms import AddCopyFeedForm, EditFeedForm
from app.feed.util import feeds_for_form
from app.inoculation import inoculation
from app.models import Feed, FeedMember, FeedItem, Post, Community, read_posts, utcnow, NotificationSubscription, \
    CommunityMember, User, FeedJoinRequest
from app.utils import show_ban_message, piefed_markdown_to_lemmy_markdown, markdown_to_html, render_template, user_filters_posts, \
    blocked_domains, blocked_instances, blocked_communities, blocked_users, communities_banned_from, moderating_communities, \
    joined_communities, menu_topics, menu_instance_feeds, menu_my_feeds, validation_required, feed_membership, get_request
from collections import namedtuple
from sqlalchemy import desc, or_
from slugify import slugify




# ----- functions -----

@bp.route('/feed/new', methods=['GET', 'POST'])
@login_required
def feed_new():
    if current_user.banned:
        return show_ban_message()

    form = AddCopyFeedForm()
    if g.site.enable_nsfw is False:
        form.nsfw.render_kw = {'disabled': True}
    if g.site.enable_nsfl is False:
        form.nsfl.render_kw = {'disabled': True}
    if not current_user.is_admin():
        form.is_instance_feed.render_kw = {'disabled': True}
    form.parent_feed_id.choices = feeds_for_form(0, current_user.id)

    if form.validate_on_submit():
        if form.url.data.strip().lower().startswith('/f/'):
            form.url.data = form.url.data[3:]
        form.url.data = slugify(form.url.data.strip(), separator='_').lower()
        private_key, public_key = RsaKeys.generate_keypair()
        feed = Feed(user_id=current_user.id, title=form.feed_name.data, name=form.url.data, machine_name=form.url.data, 
                    description=piefed_markdown_to_lemmy_markdown(form.description.data),
                    description_html=markdown_to_html(form.description.data),
                    show_posts_in_children=form.show_child_posts.data,
                    nsfw=form.nsfw.data, nsfl=form.nsfl.data,
                    private_key=private_key,
                    public_key=public_key,
                    public=form.public.data, is_instance_feed=form.is_instance_feed.data,
                    ap_profile_id='https://' + current_app.config['SERVER_NAME'] + '/f/' + form.url.data.lower(),
                    ap_public_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + form.url.data,
                    ap_followers_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + form.url.data + '/followers',
                    ap_following_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + form.url.data + '/following',
                    ap_domain=current_app.config['SERVER_NAME'],
                    subscriptions_count=1, instance_id=1)
        if form.parent_feed_id.data:
            feed.parent_feed_id = form.parent_feed_id.data
        else:
            feed.parent_feed_id = None
        icon_file = request.files['icon_file']
        if icon_file and icon_file.filename != '':
            file = save_icon_file(icon_file, directory='feeds')
            if file:
                feed.icon = file
        banner_file = request.files['banner_file']
        if banner_file and banner_file.filename != '':
            file = save_banner_file(banner_file, directory='feeds')
            if file:
                feed.image = file
        db.session.add(feed)
        db.session.commit()

        membership = FeedMember(user_id=current_user.id, feed_id=feed.id)
        db.session.add(membership)
        db.session.commit()

        flash(_('Your new Feed has been created.'))
        # cache.delete_memoized(community_membership, current_user, community)
        # cache.delete_memoized(joined_communities, current_user.id)
        # cache.delete_memoized(moderating_communities, current_user.id)
        # return redirect('/c/' + community.name)
        return redirect(url_for('main.index'))

    return render_template('feed/feed_new.html', title=_('Create a Feed'), form=form,
                           current_app=current_app, menu_topics=menu_topics(), menu_instance_feeds=menu_instance_feeds(), 
                           menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None)


@bp.route('/feed/<int:feed_id>/edit', methods=['GET','POST'])
@login_required
def feed_edit(feed_id: int):
    if current_user.banned:
        return show_ban_message()
    # load the feed
    feed_to_edit = Feed.query.get_or_404(feed_id)
    # make sure the user owns this feed
    if feed_to_edit.user_id != current_user.id:
        abort(404)
    edit_feed_form = EditFeedForm()
    edit_feed_form.parent_feed_id.choices = feeds_for_form(feed_id, current_user.id)

    if not current_user.is_admin():
        edit_feed_form.is_instance_feed.render_kw = {'disabled': True}
    
    if edit_feed_form.validate_on_submit():
        feed_to_edit.title = edit_feed_form.feed_name.data
        feed_to_edit.name = edit_feed_form.url.data
        feed_to_edit.description = piefed_markdown_to_lemmy_markdown(edit_feed_form.description.data)
        feed_to_edit.description_html = markdown_to_html(edit_feed_form.description.data)
        feed_to_edit.show_posts_in_children = edit_feed_form.show_child_posts.data
        if edit_feed_form.parent_feed_id.data:
            feed_to_edit.parent_feed_id = edit_feed_form.parent_feed_id.data
        else:
            feed_to_edit.parent_feed_id = None
        icon_file = request.files['icon_file']
        if icon_file and icon_file.filename != '':
            file = save_icon_file(icon_file, directory='feeds')
            if file:
                feed_to_edit.icon = file
        banner_file = request.files['banner_file']
        if banner_file and banner_file.filename != '':
            file = save_banner_file(banner_file, directory='feeds')
            if file:
                feed_to_edit.image = file
        if g.site.enable_nsfw:
            feed_to_edit.nsfw = edit_feed_form.nsfw.data
        if g.site.enable_nsfl:
            feed_to_edit.nsfl = edit_feed_form.nsfl.data
        feed_to_edit.public = edit_feed_form.public.data
        feed_to_edit.is_instance_feed = edit_feed_form.is_instance_feed.data
        db.session.add(feed_to_edit)
        db.session.commit()

        flash(_('Congrats, your Feed edit has been saved!'))
        return redirect(url_for('main.index'))

    # add the current data to the form
    edit_feed_form.feed_name.data = feed_to_edit.title
    edit_feed_form.url.data = feed_to_edit.name
    edit_feed_form.description.data = feed_to_edit.description
    edit_feed_form.show_child_posts.data = feed_to_edit.show_posts_in_children
    if g.site.enable_nsfw is False:
        edit_feed_form.nsfw.render_kw = {'disabled': True}
    else:
        edit_feed_form.nsfw.data = feed_to_edit.nsfw
    if g.site.enable_nsfl is False:
        edit_feed_form.nsfl.render_kw = {'disabled': True}
    else:
        edit_feed_form.nsfw.data = feed_to_edit.nsfw
    edit_feed_form.public.data = feed_to_edit.public
    edit_feed_form.is_instance_feed.data = feed_to_edit.is_instance_feed

    return render_template('feed/feed_edit.html', form=edit_feed_form, menu_topics=menu_topics(), menu_instance_feeds=menu_instance_feeds(), 
                           menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None)


@bp.route('/feed/<int:feed_id>/delete', methods=['GET','POST'])
@login_required
def feed_delete(feed_id: int):
    # get the user_id
    user_id = int(request.args.get('user_id'))
    # get the feed
    feed = Feed.query.get_or_404(feed_id)

    # is it an instance_feed?
    instance_feed = feed.is_instance_feed

    # does the user own the feed
    if feed.user_id != user_id:
        abort(404)

    # strip out any feedmembers before deleting
    feed_members = FeedMember.query.filter_by(feed_id=feed.id)
    for fm in feed_members.all():
        db.session.delete(fm)

    # delete the feed if its empty
    if feed.num_communities == 0:
        db.session.delete(feed)
        flash(_('Feed deleted'))
    else:
        flash(_('Cannot delete feed with communities assigned to it.', 'error'))

    # commit the  removal changes
    db.session.commit()

    # clear instance feeds for dropdown menu cache
    if instance_feed:
        cache.delete_memoized(menu_instance_feeds)

    # send the user back to the page they came from or main
    # Get the referrer from the request headers
    referrer = request.referrer

    # If the referrer exists and is not the same as the current request URL, redirect to the referrer
    if referrer and referrer != request.url:
        return redirect(referrer)

    # If referrer is not available or is the same as the current request URL, redirect to the default URL
    return redirect(url_for('main.index'))


@bp.route('/feed/<int:feed_id>/copy', methods=['GET','POST'])
@login_required
def feed_copy(feed_id: int):
    if current_user.banned:
        return show_ban_message()
    # load the feed
    feed_to_copy = Feed.query.get_or_404(feed_id)
    copy_feed_form = AddCopyFeedForm()
    copy_feed_form.parent_feed_id.choices = feeds_for_form(0, current_user.id)

    if not current_user.is_admin():
        copy_feed_form.is_instance_feed.render_kw = {'disabled': True}
    
    if copy_feed_form.validate_on_submit():
        if copy_feed_form.url.data.strip().lower().startswith('/f/'):
            copy_feed_form.url.data = copy_feed_form.url.data[3:]
        copy_feed_form.url.data = slugify(copy_feed_form.url.data.strip(), separator='_').lower()
        private_key, public_key = RsaKeys.generate_keypair()
        feed = Feed(user_id=current_user.id, title=copy_feed_form.feed_name.data, name=copy_feed_form.url.data, machine_name=copy_feed_form.url.data, 
                    description=piefed_markdown_to_lemmy_markdown(copy_feed_form.description.data),
                    description_html=markdown_to_html(copy_feed_form.description.data),
                    show_posts_in_children=copy_feed_form.show_child_posts.data,
                    nsfw=copy_feed_form.nsfw.data, nsfl=copy_feed_form.nsfl.data,
                    private_key=private_key,
                    public_key=public_key,
                    public=copy_feed_form.public.data, is_instance_feed=copy_feed_form.is_instance_feed.data,
                    ap_profile_id='https://' + current_app.config['SERVER_NAME'] + '/f/' + copy_feed_form.url.data.lower(),
                    ap_public_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + copy_feed_form.url.data,
                    ap_followers_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + copy_feed_form.url.data + '/followers',
                    ap_following_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + copy_feed_form.url.data + '/following',
                    ap_domain=current_app.config['SERVER_NAME'],
                    subscriptions_count=1, instance_id=1)
        if copy_feed_form.parent_feed_id.data:
            feed.parent_feed_id = copy_feed_form.parent_feed_id.data
        else:
            feed.parent_feed_id = None
        icon_file = request.files['icon_file']
        if icon_file and icon_file.filename != '':
            file = save_icon_file(icon_file, directory='feeds')
            if file:
                feed.icon = file
        banner_file = request.files['banner_file']
        if banner_file and banner_file.filename != '':
            file = save_banner_file(banner_file, directory='feeds')
            if file:
                feed.image = file
        db.session.add(feed)
        db.session.commit()

        # get the FeedItems from the feed being copied and 
        # make sure they all come over to the new Feed
        old_feed_items = FeedItem.query.join(Feed, FeedItem.feed_id == feed_to_copy.id).all()
        for item in old_feed_items:
            fi = FeedItem(feed_id=feed.id, community_id=item.community_id)
            db.session.add(fi)
            db.session.commit()
        

        # also subscribe the user to any community they are not already subscribed to
        member_of_ids = []
        member_of = CommunityMember.query.filter_by(user_id=current_user.id).all()
        for cm in member_of:
            member_of_ids.append(cm.community_id)
        for item in old_feed_items:
            if item.community_id not in member_of_ids:
                from app.community.routes import do_subscribe
                community = Community.query.get(item.community_id)
                actor = community.ap_id if community.ap_id else community.name
                do_subscribe(actor, current_user.id)

        feed.num_communities = len(old_feed_items)
        db.session.add(feed)
        db.session.commit()

        membership = FeedMember(user_id=current_user.id, feed_id=feed.id)
        db.session.add(membership)
        db.session.commit()

        flash(_('Your new Feed has been created.'))
        return redirect(url_for('main.index'))        

    # add the current data to the form
    copy_feed_form.feed_name.data = feed_to_copy.title
    copy_feed_form.url.data = feed_to_copy.name
    copy_feed_form.description.data = feed_to_copy.description
    copy_feed_form.show_child_posts.data = feed_to_copy.show_posts_in_children
    if g.site.enable_nsfw is False:
        copy_feed_form.nsfw.render_kw = {'disabled': True}
    else:
        copy_feed_form.nsfw.data = feed_to_copy.nsfw
    if g.site.enable_nsfl is False:
        copy_feed_form.nsfl.render_kw = {'disabled': True}
    else:
        copy_feed_form.nsfw.data = feed_to_copy.nsfw
    copy_feed_form.public.data = feed_to_copy.public
    copy_feed_form.is_instance_feed.data = feed_to_copy.is_instance_feed

    return render_template('feed/feed_copy.html', form=copy_feed_form, menu_topics=menu_topics(), menu_instance_feeds=menu_instance_feeds(), 
                           menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None)


@bp.route('/feed/<int:feed_id>/notification', methods=['GET', 'POST'])
@login_required
def feed_notification(feed_id: int):
    # Toggle whether the current user is subscribed to notifications about this feed's posts or not
    feed = Feed.query.get_or_404(feed_id)
    existing_notification = NotificationSubscription.query.filter(NotificationSubscription.entity_id == feed.id,
                                                                  NotificationSubscription.user_id == current_user.id,
                                                                  NotificationSubscription.type == NOTIF_FEED).first()
    if existing_notification:
        db.session.delete(existing_notification)
        db.session.commit()
    else:  # no subscription yet, so make one
        new_notification = NotificationSubscription(name=feed.name, user_id=current_user.id, entity_id=feed.id,
                                                    type=NOTIF_FEED)
        db.session.add(new_notification)
        db.session.commit()

    return render_template('feed/_notification_toggle.html', feed=feed)


@bp.route('/feed/add_community', methods=['GET'])
@login_required
def feed_add_community():
    # this expects a user_id, a new_feed_id, a current_feed_id,
    # and a community_id
    # it will get those and then add a community to 
    # a feed using the FeedItem model
    user_id = int(request.args.get('user_id'))
    feed_id = int(request.args.get('new_feed_id'))
    current_feed_id = int(request.args.get('current_feed_id'))
    community_id = int(request.args.get('community_id'))

    # make sure the user owns this feed
    if Feed.query.get(feed_id).user_id != user_id:
        abort(404)

    # if current_feed_id is not 0 then we are moving a community from
    # one feed to another
    if current_feed_id != 0:
        current_feed_item = FeedItem.query.filter_by(feed_id=current_feed_id).filter_by(community_id=community_id).first()
        db.session.delete(current_feed_item)
        db.session.commit()
        
        # also update the num_communities for the old feed
        current_feed = Feed.query.get(current_feed_id)
        current_feed.num_communities = current_feed.num_communities - 1
        db.session.add(current_feed)
        db.session.commit()


    # make the new feeditem and commit it
    feed_item = FeedItem(feed_id=feed_id, community_id=community_id)
    db.session.add(feed_item)
    db.session.commit()

    # also update the num_communities for the new feed
    feed = Feed.query.get(feed_id)
    feed.num_communities = feed.num_communities + 1
    db.session.add(feed)
    db.session.commit()

    # subscribe the user to the community if they are not already subscribed
    current_membership = CommunityMember.query.filter_by(user_id=user_id, community_id=community_id).first()
    if current_membership is None:
        # import do_subscribe here, otherwise we get import errors from circular import problems
        from app.community.routes import do_subscribe
        community = Community.query.get(community_id)
        actor = community.ap_id if community.ap_id else community.name
        do_subscribe(actor, user_id)

    # send the user back to the page they came from or main
    # Get the referrer from the request headers
    referrer = request.referrer

    # If the referrer exists and is not the same as the current request URL, redirect to the referrer
    if referrer and referrer != request.url:
        return redirect(referrer)

    # If referrer is not available or is the same as the current request URL, redirect to the default URL
    return redirect(url_for('main.index'))


@bp.route('/feed/remove_community', methods=['GET'])
@login_required
def feed_remove_community():
    # this takes a user_id, new_feed_id (0), current_feed_id,
    # and community_id then removes the community from the feed

    # get the user id
    user_id = int(request.args.get('user_id'))
    # get the community id
    community_id = int(request.args.get('community_id'))
    # get the current_feed
    current_feed_id = int(request.args.get('current_feed_id'))
    # get the new_feed_id 
    new_feed_id = int(request.args.get('new_feed_id'))
    # get the user's feeds
    # user_feeds = Feed.query.filter_by(user_id=user_id).all()

    # make sure the user owns this feed
    if Feed.query.get(current_feed_id).user_id != user_id:
        abort(404)
    # if new_feed_id is 0, remove the right FeedItem
    # if its not 0 abort
    if new_feed_id == 0:
        current_feed_item = FeedItem.query.filter_by(feed_id=current_feed_id).filter_by(community_id=community_id).first()
        db.session.delete(current_feed_item)
        db.session.commit()
        # also update the num_communities for the old feed
        current_feed = Feed.query.get(current_feed_id)
        current_feed.num_communities = current_feed.num_communities - 1
        db.session.add(current_feed)
        db.session.commit()
    else:
        abort(404)

    # send the user back to the page they came from or main
    # back(url_for('main.index'))
    # Get the referrer from the request headers
    referrer = request.referrer

    # If the referrer exists and is not the same as the current request URL, redirect to the referrer
    if referrer and referrer != request.url:
        return redirect(referrer)

    # If referrer is not available or is the same as the current request URL, redirect to the default URL
    return redirect(url_for('main.index'))        


@bp.route('/feed/list', methods=['GET'])
@login_required
def feed_list():
    # this takes a user id, community id, and current_feed id, 
    # and returns a set of html entries of the users feeds 

    # get the user id
    user_id = int(request.args.get('user_id'))
    # get the community id
    community_id = int(request.args.get('community_id'))
    # get the current_feed
    current_feed_id = int(request.args.get('current_feed_id'))
    # get the user's feeds
    user_feeds = Feed.query.filter_by(user_id=user_id).all()

    # setup html base to send back
    options_html = ""

    # add the none option if already in a feed
    if current_feed_id != 0:
        options_html = options_html + f'<li><a class="dropdown-item" href="/feed/remove_community?user_id={user_id}&new_feed_id=0&current_feed_id={current_feed_id}&community_id={community_id}">None</li>'
    
    # for loop to add the rest of the options to the html
    for feed in user_feeds:
        # skip the current_feed if it has one
        if feed.id == current_feed_id:
            continue
        options_html = options_html + f'<li><a class="dropdown-item" href="/feed/add_community?user_id={user_id}&new_feed_id={feed.id}&current_feed_id={current_feed_id}&community_id={community_id}">{feed.name}</li>'
    
    return options_html


# @bp.route('/f/<actor>', methods=['GET']) - defined in activitypub/routes.py, which calls this function for user requests. A bit weird.
def show_feed(feed):
    # if the feed is private abort, unless the logged in user is the owner of the feed
    if not feed.public:
        if current_user.is_authenticated and current_user.id == feed.user_id:
            ...
        else:
            flash(_('That feed is not public. Try one of these!'))
            return redirect(url_for('main.public_feeds'))

    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', '' if current_user.is_anonymous else current_user.default_sort)
    low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'
    post_layout = request.args.get('layout', 'list' if not low_bandwidth else None)

    
    breadcrumbs = []
    existing_url = '/f'
    # check the path to see if this is a sub feed of some other feed
    if '/' in feed.path():
        feed_url_parts = feed.path().split('/')
        last_feed_machine_name = feed_url_parts[-1]
        breadcrumb_feed = None
        for url_part in feed_url_parts:
            breadcrumb_feed = Feed.query.filter(Feed.machine_name == url_part.strip().lower()).first()
            if breadcrumb_feed:
                breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
                breadcrumb.text = breadcrumb_feed.name
                breadcrumb.url = f"{existing_url}/{breadcrumb_feed.machine_name}" if breadcrumb_feed.machine_name != last_feed_machine_name else ''
                breadcrumbs.append(breadcrumb)
                existing_url = breadcrumb.url
            else:
                abort(404)
    else:
        breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
        breadcrumb.text = feed.name
        breadcrumb.url = f"{existing_url}/{feed.machine_name}"
        breadcrumbs.append(breadcrumb)

    current_feed = feed

    if current_feed:
        # get the feed_ids
        if current_feed.show_posts_in_children:    # include posts from child feeds
            feed_ids = get_all_child_feed_ids(current_feed)
        else:
            feed_ids = [current_feed.id]
        
        # for each feed get the community ids (FeedItem) in the feed
        # used for the posts searching
        feed_community_ids = []
        for fid in feed_ids:
            feed_items = FeedItem.query.join(Feed, FeedItem.feed_id == fid).all()
            for item in feed_items:
                feed_community_ids.append(item.community_id)

        posts = Post.query.join(Community, Post.community_id == Community.id).filter(Community.id.in_(feed_community_ids),
                                                                                     Community.banned == False)

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
            posts = posts.filter(Post.deleted == False)
            content_filters = user_filters_posts(current_user.id)

            # filter blocked domains and instances
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

            banned_from = communities_banned_from(current_user.id)
            if banned_from:
                posts = posts.filter(Post.community_id.not_in(banned_from))

        # sorting
        if sort == '' or sort == 'hot':
            posts = posts.order_by(desc(Post.ranking)).order_by(desc(Post.posted_at))
        elif sort == 'top':
            posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=7)).order_by(desc(Post.up_votes - Post.down_votes))
        elif sort == 'new':
            posts = posts.order_by(desc(Post.posted_at))
        elif sort == 'active':
            posts = posts.order_by(desc(Post.last_active))

        # paging
        per_page = 100
        if post_layout == 'masonry':
            per_page = 200
        elif post_layout == 'masonry_wide':
            per_page = 300
        posts = posts.paginate(page=page, per_page=per_page, error_out=False)

        feed_communities = Community.query.filter(Community.id.in_(feed_community_ids),Community.banned == False)

        next_url = url_for('activitypub.feed_profile', actor=feed.ap_id if feed.ap_id is not None else feed.name,
                       page=posts.next_num, sort=sort, layout=post_layout) if posts.has_next else None
        prev_url = url_for('activitypub.feed_profile', actor=feed.ap_id if feed.ap_id is not None else feed.name,
                       page=posts.prev_num, sort=sort, layout=post_layout) if posts.has_prev and page != 1 else None

        sub_feeds = Feed.query.filter_by(parent_feed_id=current_feed.id).order_by(Feed.name).all()

        return render_template('feed/show_feed.html', title=_(current_feed.name), posts=posts, feed=current_feed, sort=sort,
                               page=page, post_layout=post_layout, next_url=next_url, prev_url=prev_url,
                               feed_communities=feed_communities, content_filters=content_filters,
                               sub_feeds=sub_feeds, feed_path=feed.path(), breadcrumbs=breadcrumbs,
                               rss_feed=f"https://{current_app.config['SERVER_NAME']}/f/{feed.path()}.rss",
                               rss_feed_name=f"{current_feed.name} on {g.site.name}",
                               show_post_community=True, moderating_communities=moderating_communities(current_user.get_id()),
                               joined_communities=joined_communities(current_user.get_id()),
                               menu_topics=menu_topics(),
                               inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None,
                               menu_instance_feeds=menu_instance_feeds(), 
                               menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None,
                               POST_TYPE_LINK=POST_TYPE_LINK, POST_TYPE_IMAGE=POST_TYPE_IMAGE,
                               POST_TYPE_VIDEO=POST_TYPE_VIDEO,
                               SUBSCRIPTION_OWNER=SUBSCRIPTION_OWNER, SUBSCRIPTION_MODERATOR=SUBSCRIPTION_MODERATOR,
                               )
    else:
        abort(404)


def get_all_child_feed_ids(feed: Feed) -> List[int]:
    # recurse down the feed tree, gathering all the feed IDs found
    feed_ids = [feed.id]
    for child_feed in Feed.query.filter(Feed.parent_feed_id == feed.id):
        feed_ids.extend(get_all_child_feed_ids(child_feed))
    return feed_ids


@bp.route('/f/<feed_name>/submit', methods=['GET', 'POST'])
@login_required
@validation_required
def feed_create_post(feed_name):
    feed = Feed.query.filter(Feed.machine_name == feed_name.strip().lower()).first()
    if not feed:
        abort(404)
    
    feed_community_ids = []
    feed_items = FeedItem.query.join(Feed, FeedItem.feed_id == feed.id).all()
    for item in feed_items:
        feed_community_ids.append(item.community_id)

    communities = Community.query.filter(Community.id.in_(feed_community_ids)).filter_by(banned=False).order_by(Community.title).all()
    sub_feed_community_ids = []
    child_feeds = [feed.id for feed in Feed.query.filter(Feed.parent_feed_id == feed.id).all()]
    for cf in child_feeds:
        feed_items = FeedItem.query.join(Feed, FeedItem.feed_id == cf.id).all()
        for item in feed_items:
            sub_feed_community_ids.append(item.community_id)

    sub_communities = Community.query.filter_by(banned=False).filter(Community.id.in_(sub_feed_community_ids)).order_by(Community.title).all()
    if request.form.get('community_id', '') != '':
        community = Community.query.get_or_404(int(request.form.get('community_id')))
        return redirect(url_for('community.join_then_add', actor=community.link()))
    return render_template('feed/feed_create_post.html', communities=communities, sub_communities=sub_communities,
                           feed=feed,
                           moderating_communities=moderating_communities(current_user.get_id()),
                           joined_communities=joined_communities(current_user.get_id()),
                           menu_topics=menu_topics(),
                           menu_instance_feeds=menu_instance_feeds(), 
                           menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None,
                           SUBSCRIPTION_OWNER=SUBSCRIPTION_OWNER, SUBSCRIPTION_MODERATOR=SUBSCRIPTION_MODERATOR)


@bp.route('/<actor>/subscribe', methods=['GET'])
@login_required
@validation_required
def subscribe(actor):
    do_feed_subscribe(actor, current_user.id)
    referrer = request.headers.get('Referer', None)
    if referrer is not None:
        return redirect(referrer)
    else:
        return redirect('/f/' + actor)


@celery.task
def do_feed_subscribe(actor, user_id):
    remote = False
    actor = actor.strip()
    user = User.query.get(user_id)
    # pre_load_message = {}
    if '@' in actor:
        feed = Feed.query.filter_by(ap_id=actor).first()
        remote = True
    else:
        feed = Feed.query.filter_by(name=actor, ap_id=None).first()

    if feed is not None:
        if feed_membership(user, feed) != SUBSCRIPTION_MEMBER and feed_membership(user, feed) != SUBSCRIPTION_PENDING:
            success = True

            # for local feeds, joining is instant
            member = FeedMember(user_id=user.id, feed_id=feed.id)
            db.session.add(member)
            feed.subscriptions_count += 1
            db.session.commit()

            # also subscribe the user to the feeditem communities
            from app.community.routes import do_subscribe
            feed_items = FeedItem.query.filter_by(feed_id=feed.id).all()
            for fi in feed_items:
                community = Community.query.get(fi.community_id)
                actor = community.ap_id if community.ap_id else community.name
                do_subscribe(actor, user.id)
 
            # feed is remote
            if remote:
                # send ActivityPub message to remote feed, asking to follow. Accept message will be sent to our shared inbox
                join_request = FeedJoinRequest(user_id=user.id, feed_id=feed.id)
                db.session.add(join_request)
                db.session.commit()
                if feed.instance.online():
                    follow = {
                      "actor": user.public_url(),
                      "to": [feed.public_url()],
                      "object": feed.public_url(),
                      "type": "Follow",
                      "id": f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
                    }
                    success = post_request(feed.ap_inbox_url, follow, user.private_key,
                                                           user.public_url() + '#main-key', timeout=10)
                    
                    # reach out and get the feeditems from the remote /following collection
                    res = get_request(feed.ap_following_url)
                    following_collection = res.json()

                    # for each of those subscribe the user to the communities
                    for fci in following_collection['items']:
                        community_ap_id = fci 
                        community = find_actor_or_create(community_ap_id, community_only=True)
                        if community and isinstance(community, Community):
                            actor = community.ap_id if community.ap_id else community.name
                            do_subscribe(actor, user.id)
                            # also make a feeditem in the local db
                            feed_item = FeedItem(feed_id=feed.id, community_id=community.id)
                            db.session.add(feed_item)
                            db.session.commit()

                if success is False or isinstance(success, str):
                    if 'is not in allowlist' in success:
                        msg_to_user = f'{feed.instance.domain} does not allow us to subscribe to their feeds.'
                        flash(_(msg_to_user), 'error')
                        # if not admin_preload:
                        #     flash(_(msg_to_user), 'error')
                        # else:
                        #     pre_load_message['status'] = msg_to_user
                    else:
                        msg_to_user = "There was a problem while trying to communicate with remote server. If other people have already subscribed to this feed it won't matter."
                        flash(_(msg_to_user), 'error')
                        # if not admin_preload:
                        #     flash(_(msg_to_user), 'error')
                        # else:
                        #     pre_load_message['status'] = msg_to_user

            if success is True:
                flash('You subscribed to ' + feed.title)
                # if not admin_preload:
                #     flash('You joined ' + community.title)
                # else:
                #     pre_load_message['status'] = 'joined'
        else:
            msg_to_user = "Already subscribed, or subscription pending"
            flash(_(msg_to_user))
            # if admin_preload:
            #     pre_load_message['status'] = 'already subscribed, or subsciption pending'

        cache.delete_memoized(feed_membership, user, feed)
        cache.delete_memoized(joined_communities, user.id)
        # if admin_preload:
        #     return pre_load_message
    else:
        abort(404)
        # if not admin_preload:
        #     abort(404)
        # else:
        #     pre_load_message['community'] = actor
        #     pre_load_message['status'] = 'community not found'
        #     return pre_load_message

