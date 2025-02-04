# ----- imports -----
import flask
from flask import g, current_app, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from flask_babel import _
from app import db
from app.activitypub.signature import RsaKeys
from app.community.util import save_icon_file, save_banner_file
from app.feed import  bp
from app.feed.forms import AddFeedForm
from app.models import Feed, FeedMember, FeedItem
from app.utils import show_ban_message, piefed_markdown_to_lemmy_markdown, markdown_to_html, render_template, back
from slugify import slugify




# ----- functions -----

@bp.route('/feed/new', methods=['GET', 'POST'])
@login_required
def feed_new():
    if current_user.banned:
        return show_ban_message()
    form = AddFeedForm()
    if g.site.enable_nsfw is False:
        form.nsfw.render_kw = {'disabled': True}
    if g.site.enable_nsfl is False:
        form.nsfl.render_kw = {'disabled': True}

    if form.validate_on_submit():
        if form.url.data.strip().lower().startswith('/f/'):
            form.url.data = form.url.data[3:]
        form.url.data = slugify(form.url.data.strip(), separator='_').lower()
        private_key, public_key = RsaKeys.generate_keypair()
        feed = Feed(user_id=current_user.id, title=form.feed_name.data, name=form.url.data, machine_name=form.url.data, 
                    description=piefed_markdown_to_lemmy_markdown(form.description.data),
                    description_html=markdown_to_html(form.description.data),
                    nsfw=form.nsfw.data, nsfl=form.nsfl.data,
                    private_key=private_key,
                    public_key=public_key,
                    ap_profile_id='https://' + current_app.config['SERVER_NAME'] + '/f/' + form.url.data.lower(),
                    ap_public_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + form.url.data,
                    ap_followers_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + form.url.data + '/followers',
                    ap_following_url='https://' + current_app.config['SERVER_NAME'] + '/f/' + form.url.data + '/following',
                    ap_domain=current_app.config['SERVER_NAME'],
                    subscriptions_count=1, instance_id=1)
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
                           current_app=current_app)


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

    # make sure the user has owns this feed
    if Feed.query.get(feed_id).user_id != user_id:
        abort(404)

    # if current_feed_id is not 0 then we are moving a community from
    # one feed to another
    if current_feed_id != 0:
        current_feed_item = FeedItem.query.filter_by(feed_id=current_feed_id).filter_by(community_id=community_id).first()
        db.session.delete(current_feed_item)
        db.session.commit()

    # make the new feeditem and commit it
    feed_item = FeedItem(feed_id=feed_id, community_id=community_id)
    db.session.add(feed_item)
    db.session.commit()

    # send the user back to the page they came from or main
    # back(url_for('main.index'))
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
    user_feeds = Feed.query.filter_by(user_id=user_id).all()
    # make sure the user owns this feed
    if Feed.query.get(current_feed_id).user_id != user_id:
        abort(404)
    # if new_feed_id is 0, remove the right FeedItem
    # if its not 0 abort
    if new_feed_id == 0:
        current_feed_item = FeedItem.query.filter_by(feed_id=current_feed_id).filter_by(community_id=community_id).first()
        db.session.delete(current_feed_item)
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
    options_html = options_html + f'<li><a class="dropdown-item" href="/feed/remove_community?user_id={user_id}&new_feed_id=0&current_feed_id={current_feed_id}&community_id={community_id}">None</li>'
    
    # for loop to add the rest of the options to the html
    for feed in user_feeds:
        # skip the current_feed if it has one
        if feed.id == current_feed_id:
            continue
        options_html = options_html + f'<li><a class="dropdown-item" href="/feed/add_community?user_id={user_id}&new_feed_id={feed.id}&current_feed_id={current_feed_id}&community_id={community_id}">{feed.name}</li>'
    
    return options_html

