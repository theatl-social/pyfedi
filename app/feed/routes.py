# ----- imports -----
import flask
from datetime import timedelta
from random import randint
from typing import List
from flask import g, current_app, request, redirect, url_for, flash, abort, Markup
from flask_login import current_user, login_required
from flask_babel import _
from app import db, cache, celery
from app.activitypub.signature import RsaKeys, post_request, default_context
from app.activitypub.util import find_actor_or_create, extract_domain_and_actor
from app.community.util import save_icon_file, save_banner_file
from app.constants import SUBSCRIPTION_OWNER, SUBSCRIPTION_MODERATOR, POST_TYPE_IMAGE, \
    POST_TYPE_LINK, POST_TYPE_VIDEO, NOTIF_FEED, SUBSCRIPTION_MEMBER, SUBSCRIPTION_PENDING
from app.feed import  bp
from app.feed.forms import AddCopyFeedForm, EditFeedForm, SearchRemoteFeed
from app.feed.util import feeds_for_form, search_for_feed, actor_to_feed, feed_communities_for_edit, \
    existing_communities, form_communities_to_ids
from app.inoculation import inoculation
from app.models import Feed, FeedMember, FeedItem, Post, Community, read_posts, utcnow, NotificationSubscription, \
    CommunityMember, User, FeedJoinRequest, Instance, Topic, CommunityJoinRequest
from app.utils import show_ban_message, piefed_markdown_to_lemmy_markdown, markdown_to_html, render_template, \
    user_filters_posts, \
    blocked_domains, blocked_instances, blocked_communities, blocked_users, communities_banned_from, \
    moderating_communities, \
    joined_communities, menu_topics, menu_instance_feeds, menu_my_feeds, validation_required, feed_membership, \
    get_request, \
    gibberish, get_task_session, instance_banned, menu_subscribed_feeds, referrer, community_membership
from collections import namedtuple
from sqlalchemy import desc, or_, text
from slugify import slugify


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

        membership = FeedMember(user_id=current_user.id, feed_id=feed.id, is_owner=True)
        db.session.add(membership)
        db.session.commit()

        new_communities = form_communities_to_ids(form.communities.data)  # the communities that are in the feed now

        for added_community in new_communities:
            _feed_add_community(added_community, 0, feed.id, current_user.id)

        flash(_('Your new Feed has been created.'))
        return redirect(url_for('user.user_myfeeds'))

    # Create Feed from a topic
    if request.args.get('topic_id'):
        topic = Topic.query.get(request.args.get('topic_id'))
        community_apids = []
        for community in topic.communities:
            community_apids.append(community.lemmy_link().replace('!', ''))
        form.feed_name.data = topic.name
        form.url.data = topic.machine_name
        form.communities.data = '\n'.join(community_apids)

    return render_template('feed/feed_new.html', title=_('Create a Feed'), form=form,
                           current_app=current_app, menu_topics=menu_topics(), menu_instance_feeds=menu_instance_feeds(), 
                           menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None,
                           menu_subscribed_feeds=menu_subscribed_feeds(current_user.id) if current_user.is_authenticated else None,
                           )


@bp.route('/feed/add_remote', methods=['GET','POST'])
@login_required
def feed_add_remote():
    if current_user.banned:
        return show_ban_message()
    form = SearchRemoteFeed()
    new_feed = None
    if form.validate_on_submit():
        address = form.address.data.strip().lower()

        if address.startswith('~') and '@' in address:
            try:
                new_feed = search_for_feed(address)
            except Exception as e:
                if 'is blocked.' in str(e):
                    flash(_('Sorry, that instance is blocked, check https://gui.fediseer.com/ for reasons.'), 'warning')
        elif address.startswith('@') and '@' in address[1:]:
            # todo: the user is searching for a person instead
            ...
        elif '@' in address:
            new_feed = search_for_feed('~' + address)
        elif address.startswith('https://'):
            server, feed = extract_domain_and_actor(address)
            new_feed = search_for_feed('~' + feed + '@' + server)
        else:
            message = Markup(
                'Accepted address formats: ~feedname@server.name or https://server.name/f/feedname.')
            flash(message, 'error')
        if new_feed is None:
            if g.site.enable_nsfw:
                flash(_('Feed not found.'), 'warning')
            else:
                flash(_('Feed not found. If you are searching for a nsfw feed it is blocked by this instance.'), 'warning')

    return render_template('feed/add_remote.html',
                           title=_('Add remote feed'), form=form, new_feed=new_feed,
                           subscribed=feed_membership(current_user, new_feed) >= SUBSCRIPTION_MEMBER, moderating_communities=moderating_communities(current_user.get_id()),
                           joined_communities=joined_communities(current_user.get_id()),
                           menu_topics=menu_topics(),
                           site=g.site, menu_instance_feeds=menu_instance_feeds(), 
                           menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None,
                           menu_subscribed_feeds=menu_subscribed_feeds(current_user.id) if current_user.is_authenticated else None,
                           )    


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
        feed_to_edit.machine_name = edit_feed_form.url.data
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
        if current_user.is_admin():
            cache.delete_memoized(menu_instance_feeds)
        db.session.add(feed_to_edit)
        db.session.commit()

        # Update FeedItems based on whatever has changed in the form.communities field
        old_communities = set(existing_communities(feed_to_edit.id))    # the communities that were in the feed before the edit was made
        new_communities = form_communities_to_ids(edit_feed_form.communities.data)  # the communities that are in the feed now
        added_communities = new_communities - old_communities
        removed_communities = old_communities - new_communities

        for added_community in added_communities:
            _feed_add_community(added_community, 0, feed_to_edit.id, current_user.id)

        for removed_community in removed_communities:
            _feed_remove_community(removed_community, feed_to_edit.id, current_user.id)

        flash(_('Settings saved.'))
        return redirect(referrer())

    # add the current data to the form
    edit_feed_form.feed_name.data = feed_to_edit.title
    edit_feed_form.url.data = feed_to_edit.name
    edit_feed_form.description.data = feed_to_edit.description
    edit_feed_form.communities.data = feed_communities_for_edit(feed_to_edit.id)
    edit_feed_form.show_child_posts.data = feed_to_edit.show_posts_in_children
    edit_feed_form.parent_feed_id.data = feed_to_edit.parent_feed_id
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
                           menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None,
                           menu_subscribed_feeds=menu_subscribed_feeds(current_user.id) if current_user.is_authenticated else None,
                           )


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
    
    # announce the change to any potential subscribers
    # have to do it here before the feed members are cleared out
    if feed.public:
        if current_app.debug:
            announce_feed_delete_to_subscribers(user_id, feed.id)
        else:
            announce_feed_delete_to_subscribers.delay(user_id, feed.id)

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
            if item.community_id not in member_of_ids and current_user.feed_auto_follow:
                from app.community.routes import do_subscribe
                community = Community.query.get(item.community_id)
                actor = community.ap_id if community.ap_id else community.name
                do_subscribe(actor, current_user.id, joined_via_feed=True)

        feed.num_communities = len(old_feed_items)
        db.session.add(feed)
        db.session.commit()

        membership = FeedMember(user_id=current_user.id, feed_id=feed.id, is_owner=True)
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
                           menu_my_feeds=menu_my_feeds(current_user.id) if current_user.is_authenticated else None,
                           menu_subscribed_feeds=menu_subscribed_feeds(current_user.id) if current_user.is_authenticated else None,
                           )


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

    _feed_add_community(community_id, current_feed_id, feed_id, user_id)

    # send the user back to the page they came from or main
    # Get the referrer from the request headers
    referrer = request.referrer

    # If the referrer exists and is not the same as the current request URL, redirect to the referrer
    if referrer and referrer != request.url:
        return redirect(referrer)

    # If referrer is not available or is the same as the current request URL, redirect to the default URL
    return redirect(url_for('main.index'))


def _feed_add_community(community_id: int, current_feed_id: int, feed_id: int, user_id: int):
    # if current_feed_id is not 0 then we are moving a community from
    # one feed to another
    if current_feed_id != 0:
        current_feed_item = FeedItem.query.filter_by(feed_id=current_feed_id).filter_by(
            community_id=community_id).first()
        db.session.delete(current_feed_item)
        db.session.commit()

        # also update the num_communities for the old feed
        current_feed = Feed.query.get(current_feed_id)
        current_feed.num_communities = current_feed.num_communities - 1
        db.session.add(current_feed)
        db.session.commit()

        # announce the change to any potential subscribers
        if current_feed.public:
            community = Community.query.get(community_id)
            if current_app.debug:
                announce_feed_add_remove_to_subscribers("Remove", current_feed.id, community.id)
            else:
                announce_feed_add_remove_to_subscribers.delay("Remove", current_feed.id, community.id)

    # make the new feeditem and commit it
    feed_item = FeedItem(feed_id=feed_id, community_id=community_id)
    db.session.add(feed_item)
    db.session.commit()

    # also update the num_communities for the new feed
    feed = Feed.query.get(feed_id)
    feed.num_communities = feed.num_communities + 1
    db.session.add(feed)
    db.session.commit()

    # announce the change to any potential subscribers
    if feed.public:
        community = Community.query.get(community_id)
        if current_app.debug:
            announce_feed_add_remove_to_subscribers("Add", feed.id, community.id)
        else:
            announce_feed_add_remove_to_subscribers.delay("Add", feed.id, community.id)

    # subscribe the user to the community if they are not already subscribed
    current_membership = CommunityMember.query.filter_by(user_id=user_id, community_id=community_id).first()
    if current_membership is None and current_user.feed_auto_follow:
        # import do_subscribe here, otherwise we get import errors from circular import problems
        from app.community.routes import do_subscribe
        community = Community.query.get(community_id)
        actor = community.ap_id if community.ap_id else community.name
        do_subscribe(actor, user_id, joined_via_feed=True)


@bp.route('/feed/remove_community', methods=['GET'])
@login_required
def feed_remove_community():
    # this takes a user_id, new_feed_id (0), current_feed_id,
    # and community_id then removes the community from the feed
    # this is only called when changing a community from a feed to 'None'

    # get the user id
    user_id = int(request.args.get('user_id'))
    # get the community id
    community_id = int(request.args.get('community_id'))
    # get the current_feed
    current_feed_id = int(request.args.get('current_feed_id'))
    # get the new_feed_id 
    new_feed_id = int(request.args.get('new_feed_id'))

    # make sure the user owns this feed
    if Feed.query.get(current_feed_id).user_id != user_id:
        abort(403) # 403 Forbidden

    # if new_feed_id is 0, remove the right FeedItem
    # if its not 0 abort
    if new_feed_id == 0:
        _feed_remove_community(community_id, current_feed_id, user_id)
    else:
        abort(404)

    # send the user back to the page they came from or main
    # Get the referrer from the request headers
    referrer = request.referrer

    # If the referrer exists and is not the same as the current request URL, redirect to the referrer
    if referrer and referrer != request.url:
        return redirect(referrer)

    # If referrer is not available or is the same as the current request URL, redirect to the default URL
    return redirect(url_for('main.index'))


def _feed_remove_community(community_id: int, current_feed_id: int, user_id: int):
    current_feed_item = FeedItem.query.filter_by(feed_id=current_feed_id).filter_by(community_id=community_id).first()
    db.session.delete(current_feed_item)
    db.session.commit()

    # also update the num_communities for the old feed
    current_feed = Feed.query.get(current_feed_id)
    current_feed.num_communities = current_feed.num_communities - 1
    db.session.add(current_feed)
    db.session.commit()

    community = Community.query.get(community_id)
    user = User.query.get(user_id)
    cm = CommunityMember.query.filter_by(user_id=user.id, community_id=community.id).first()
    # if user.feed_auto_leave, and the user joined the community as a result of
    # adding it to a feed, then un follow the community
    if user.feed_auto_leave and cm.joined_via_feed is not None and cm.joined_via_feed:
        subscription = community_membership(user, community)
        if subscription != SUBSCRIPTION_OWNER:
            proceed = True
            # Undo the Follow
            if not community.is_local():    # this is a remote community, so activitypub is needed
                success = True
                if not community.instance.gone_forever:
                    follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{gibberish(15)}"
                    if community.instance.domain == 'a.gup.pe':
                        join_request = CommunityJoinRequest.query.filter_by(user_id=user.id, community_id=community.id).first()
                        if join_request:
                            follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
                    undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/" + gibberish(15)
                    follow = {
                        "actor": user.public_url(),
                        "to": [community.public_url()],
                        "object": community.public_url(),
                        "type": "Follow",
                        "id": follow_id
                    }
                    undo = {
                        'actor': user.public_url(),
                        'to': [community.public_url()],
                        'type': 'Undo',
                        'id': undo_id,
                        'object': follow
                    }
                    success = post_request(community.ap_inbox_url, undo, user.private_key,
                                                            user.public_url() + '#main-key', timeout=10)
                if success is False or isinstance(success, str):
                    flash('There was a problem while trying to unsubscribe', 'error')

            if proceed:
                db.session.query(CommunityMember).filter_by(user_id=user.id, community_id=community.id).delete()
                db.session.query(CommunityJoinRequest).filter_by(user_id=user.id, community_id=community.id).delete()
                community.subscriptions_count -= 1
                db.session.commit()

                flash('You have left ' + community.title)
            cache.delete_memoized(community_membership, user, community)
            cache.delete_memoized(joined_communities, user.id)
        else:
            # todo: community deletion
            flash('You need to make someone else the owner before unsubscribing.', 'warning')


    # announce the change to any potential subscribers
    if current_feed.public:
        if current_app.debug:
            announce_feed_add_remove_to_subscribers("Remove", current_feed.id, community.id)
        else:
            announce_feed_add_remove_to_subscribers.delay("Remove", current_feed.id, community.id)


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
        options_html = options_html + f'<li><a class="dropdown-item" href="/feed/add_community?user_id={user_id}&new_feed_id={feed.id}&current_feed_id={current_feed_id}&community_id={community_id}">{feed.title}</li>'
    
    return options_html


# @bp.route('/f/<actor>', methods=['GET']) - defined in activitypub/routes.py, which calls this function for user requests. A bit weird.
def show_feed(feed):
    # if the feed is private abort, unless the logged in user is the owner of the feed
    if not feed.public:
        if current_user.is_authenticated and current_user.id == feed.user_id:
            ...
        elif current_user.is_authenticated and feed.subscribed(current_user.id):
            ...
        else:
            flash(_('Could not find that feed or it is not public. Try one of these instead...'))
            return redirect(url_for('main.list_feeds'))

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
                breadcrumb.text = breadcrumb_feed.title
                breadcrumb.url = f"{existing_url}/{breadcrumb_feed.machine_name}" if breadcrumb_feed.machine_name != last_feed_machine_name else ''
                breadcrumbs.append(breadcrumb)
                existing_url = breadcrumb.url
            else:
                abort(404)
    else:
        breadcrumb = namedtuple("Breadcrumb", ['text', 'url'])
        breadcrumb.text = feed.title
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

        post_id_sql = 'SELECT p.id, p.cross_posts FROM "post" as p\nINNER JOIN "community" as c on p.community_id = c.id\n'
        post_id_where = ['c.id IN :feed_community_ids AND c.banned is false ']
        params = {'feed_community_ids': feed_community_ids}

        #posts = Post.query.join(Community, Post.community_id == Community.id).filter(Community.id.in_(feed_community_ids),
        #                                                                             Community.banned == False)

        # filter out nsfw and nsfl if desired
        if current_user.is_anonymous:
            post_id_where.append('p.from_bot is false AND p.nsfw is false AND p.nsfl is false AND p.deleted is false ')
            #posts = posts.filter(Post.from_bot == False, Post.nsfw == False, Post.nsfl == False, Post.deleted == False)
            content_filters = {}
        else:
            if current_user.ignore_bots == 1:
                post_id_where.append('p.from_bot is false ')
                #posts = posts.filter(Post.from_bot == False)
            if current_user.hide_nsfl == 1:
                #posts = posts.filter(Post.nsfl == False)
                post_id_where.append('p.nsfl is false ')
            if current_user.hide_nsfw == 1:
                #posts = posts.filter(Post.nsfw == False)
                post_id_where.append('p.nsfw is false')
            if current_user.hide_read_posts:
                ...
                # @todo: read posts
                #posts = posts.outerjoin(read_posts, (Post.id == read_posts.c.read_post_id) & (read_posts.c.user_id == current_user.id))
                #posts = posts.filter(read_posts.c.read_post_id.is_(None))  # Filter where there is no corresponding read post for the current user
            #posts = posts.filter(Post.deleted == False)
            post_id_where.append('p.deleted is false ')

            content_filters = user_filters_posts(current_user.id)

            # filter blocked domains and instances
            domains_ids = blocked_domains(current_user.id)
            if domains_ids:
                #posts = posts.filter(or_(Post.domain_id.not_in(domains_ids), Post.domain_id == None))
                post_id_where.append('(p.domain_id NOT IN :domain_ids OR p.domain_id is null) ')
                params['domain_ids'] = domains_ids
            instance_ids = blocked_instances(current_user.id)
            if instance_ids:
                #posts = posts.filter(or_(Post.instance_id.not_in(instance_ids), Post.instance_id == None))
                post_id_where.append('(p.instance_id NOT IN :instance_ids OR p.instance_id is null) ')
                params['instance_ids'] = instance_ids
            community_ids = blocked_communities(current_user.id)
            if community_ids:
                #posts = posts.filter(Post.community_id.not_in(community_ids))
                post_id_where.append('p.community_id NOT IN :community_ids ')
                params['community_ids'] = community_ids
            # filter blocked users
            blocked_accounts = blocked_users(current_user.id)
            if blocked_accounts:
                #posts = posts.filter(Post.user_id.not_in(blocked_accounts))
                post_id_where.append('p.user_id NOT IN :blocked_accounts ')
                params['blocked_accounts'] = blocked_accounts


            banned_from = communities_banned_from(current_user.id)
            if banned_from:
                #posts = posts.filter(Post.community_id.not_in(banned_from))
                post_id_where.append('p.community_id NOT IN :banned_from ')
                params['banned_from'] = banned_from

        # sorting
        post_id_sort = ''
        if sort == '' or sort == 'hot':
            #posts = posts.order_by(desc(Post.ranking)).order_by(desc(Post.posted_at))
            post_id_sort = 'ORDER BY p.ranking DESC, p.posted_at DESC'
        elif sort == 'top':
            #posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=7)).order_by(desc(Post.up_votes - Post.down_votes))
            post_id_where.append('p.posted_at > :top_cutoff ')
            post_id_sort = 'ORDER BY p.up_votes - p.down_votes DESC'
            params['top_cutoff'] = utcnow() - timedelta(days=7)
        elif sort == 'new':
            #posts = posts.order_by(desc(Post.posted_at))
            post_id_sort = 'ORDER BY p.posted_at'
        elif sort == 'active':
            #posts = posts.order_by(desc(Post.last_active))
            post_id_sort = 'ORDER BY p.last_active'

        final_post_id_sql = f"{post_id_sql}{' AND '.join(post_id_where)}\n{post_id_sort}\nLIMIT 200"

        post_ids = db.session.execute(text(final_post_id_sql), params)

        # paging
        per_page = 20
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
                               menu_subscribed_feeds=menu_subscribed_feeds(current_user.id) if current_user.is_authenticated else None,
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
    for cf_id in child_feeds:
        feed_items = FeedItem.query.join(Feed, FeedItem.feed_id == cf_id).all()
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
                           menu_subscribed_feeds=menu_subscribed_feeds(current_user.id) if current_user.is_authenticated else None,
                           SUBSCRIPTION_OWNER=SUBSCRIPTION_OWNER, SUBSCRIPTION_MODERATOR=SUBSCRIPTION_MODERATOR)


@bp.route('/feed/<actor>/subscribe', methods=['GET'])
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
                if current_app.debug:
                    do_subscribe(actor, user.id, joined_via_feed=True)
                else:
                    do_subscribe.delay(actor, user.id, joined_via_feed=True)
 
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
                            do_subscribe(actor, user.id, joined_via_feed=True)
                            # also make a feeditem in the local db
                            feed_item = FeedItem(feed_id=feed.id, community_id=community.id)
                            db.session.add(feed_item)
                            db.session.commit()

                if success is False or isinstance(success, str):
                    if 'is not in allowlist' in success:
                        msg_to_user = f'{feed.instance.domain} does not allow us to subscribe to their feeds.'
                        flash(_(msg_to_user), 'error')
                    else:
                        msg_to_user = "There was a problem while trying to communicate with remote server. If other people have already subscribed to this feed it won't matter."
                        flash(_(msg_to_user), 'error')

            if success is True:
                flash('You subscribed to ' + feed.title)
        else:
            msg_to_user = "Already subscribed, or subscription pending"
            flash(_(msg_to_user))

        cache.delete_memoized(feed_membership, user, feed)
        cache.delete_memoized(joined_communities, user.id)
    else:
        abort(404)


@bp.route('/<actor>/unsubscribe', methods=['GET'])
@login_required
def feed_unsubscribe(actor):
    feed = actor_to_feed(actor)

    if feed is not None:
        subscription = feed_membership(current_user, feed)
        if subscription:
            if subscription != SUBSCRIPTION_OWNER:
                proceed = True
                # Undo the Follow
                if '@' in actor:    # this is a remote feed, so activitypub is needed
                    success = True
                    if not feed.instance.gone_forever:
                        follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{gibberish(15)}"
                        if feed.instance.domain == 'a.gup.pe':
                            join_request = FeedJoinRequest.query.filter_by(user_id=current_user.id, feed_id=feed.id).first()
                            if join_request:
                                follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
                        undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/" + gibberish(15)
                        follow = {
                          "actor": current_user.public_url(),
                          "to": [feed.public_url()],
                          "object": feed.public_url(),
                          "type": "Follow",
                          "id": follow_id
                        }
                        undo = {
                          'actor': current_user.public_url(),
                          'to': [feed.public_url()],
                          'type': 'Undo',
                          'id': undo_id,
                          'object': follow
                        }
                        success = post_request(feed.ap_inbox_url, undo, current_user.private_key,
                                                               current_user.public_url() + '#main-key', timeout=10)
                    if success is False or isinstance(success, str):
                        flash('There was a problem while trying to unsubscribe', 'error')

                if proceed:
                    db.session.query(FeedMember).filter_by(user_id=current_user.id, feed_id=feed.id).delete()
                    db.session.query(FeedJoinRequest).filter_by(user_id=current_user.id, feed_id=feed.id).delete()
                    feed.subscriptions_count -= 1
                    db.session.commit()

                    # Remove the account from each community in the feed
                    if current_user.feed_auto_leave:
                        for feed_item in FeedItem.query.filter_by(feed_id=feed.id).all():
                            membership = CommunityMember.query.filter_by(user_id=current_user.id, community_id=feed_item.community_id).first()
                            if membership and membership.joined_via_feed:
                                db.session.query(CommunityMember).filter_by(user_id=current_user.id, community_id=feed_item.community_id).delete()
                            db.session.query(CommunityJoinRequest).filter_by(user_id=current_user.id, community_id=feed_item.community_id).delete()
                            cache.delete_memoized(community_membership, current_user, Community.query.get(feed_item.community_id))
                        db.session.commit()

                    flash('You have left ' + feed.title)
                cache.delete_memoized(feed_membership, current_user, feed)
                cache.delete_memoized(joined_communities, current_user.id)
            else:
                # todo: community deletion
                flash('You need to make someone else the owner before unsubscribing.', 'warning')

        # send them back where they came from
        referrer = request.headers.get('Referer', None)
        if referrer is not None:
            return redirect(referrer)
        else:
            return redirect('/f/' + actor)
    else:
        abort(404)


@celery.task
def announce_feed_add_remove_to_subscribers(action: str, feed_id: int, community_id: int):
    # find the feed
    feed = Feed.query.get(feed_id)
    # find the community
    community = Community.query.get(community_id)
    # build the Announce json
    activity_json = {
        "@context": default_context(),
        "type": "Announce",
        "actor": feed.ap_public_url,
        "id": f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}",
    }

    # build the object json
    object_json = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": action,
        "actor": feed.ap_public_url,
        "id": f"https://{current_app.config['SERVER_NAME']}/activities/feedadd/{gibberish(15)}",
        "object": {
            "type": "Group",
            "id": community.ap_public_url
        },
        "target": {
            "type": "Collection",
            "id": feed.ap_following_url
        }
    }

    # embed the object json in the Announce json
    activity_json['object'] = object_json

    # look up the feedmembers
    feed_members = FeedMember.query.filter_by(feed_id=feed.id).all()

    # for each member
    #  - if its the owner, skip
    #  - if its a local server user, skip
    #  - if its a remote user
    # setup a db session for this task
    session = get_task_session()
    for fm in feed_members:
        fm_user = User.query.get(fm.user_id)
        if fm_user.id == feed.user_id:
            continue
        if fm_user.is_local():
            # user is local so lets auto-subscribe them to the community
            from app.community.routes import do_subscribe
            actor = community.ap_id if community.ap_id else community.name
            do_subscribe(actor, fm_user.id, joined_via_feed=True)
            continue

        # if we get here the feedmember is a remote user
        instance: Instance = session.query(Instance).get(fm_user.instance.id)
        if instance.inbox and instance.online() and not instance_banned(instance.domain):
            if post_request(instance.inbox, activity_json, feed.private_key, feed.ap_profile_id + '#main-key', timeout=10) is True:
                instance.last_successful_send = utcnow()
                instance.failures = 0
            else:
                instance.failures += 1
                instance.most_recent_attempt = utcnow()
                instance.start_trying_again = utcnow() + timedelta(seconds=instance.failures ** 4)
                if instance.failures > 10:
                    instance.dormant = True
            session.commit()
    session.close()


@celery.task
def announce_feed_delete_to_subscribers(user_id, feed_id):
    # get the user
    user = User.query.get(user_id)
    # get the feed
    feed = Feed.query.get(feed_id)
    # create the delete json
    delete_json = {
        "@context": default_context(),
        "type": "Delete",
        "actor": user.ap_public_url,
        "id": f"https://{current_app.config['SERVER_NAME']}/delete/{gibberish(15)}",
        "object": {
            "type": "Feed",
            "id": feed.ap_public_url
        }
    }

    # find the feed members
    feed_members = FeedMember.query.filter_by(feed_id=feed.id).all()
    
    # for each member
    #  - if its the owner, skip
    #  - if its a local server user, skip
    #  - if its a remote user
    session = get_task_session()
    for fm in feed_members:
        fm_user = User.query.get(fm.user_id)
        if fm_user.id == feed.user_id:
            continue
        if fm_user.is_local():
            continue
        # if we get here the feedmember is a remote user
        instance: Instance = session.query(Instance).get(fm_user.instance.id)
        if instance.inbox and instance.online() and not instance_banned(instance.domain):
            if post_request(instance.inbox, delete_json, user.private_key, user.ap_profile_id + '#main-key', timeout=10) is True:
                instance.last_successful_send = utcnow()
                instance.failures = 0
            else:
                instance.failures += 1
                instance.most_recent_attempt = utcnow()
                instance.start_trying_again = utcnow() + timedelta(seconds=instance.failures ** 4)
                if instance.failures > 10:
                    instance.dormant = True
            session.commit()
    session.close()    
