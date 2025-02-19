from flask import request, flash, json, url_for, current_app, redirect, g, abort
from flask_login import login_required, current_user
from flask_babel import _
from sqlalchemy import or_, desc

from app import limiter
from app.models import Post, Language, Community, Instance
from app.search import bp
from app.utils import moderating_communities, joined_communities, render_template, blocked_domains, blocked_instances, \
    communities_banned_from, recently_upvoted_posts, recently_downvoted_posts, blocked_users, menu_topics, \
    blocked_communities, show_ban_message
from app.community.forms import RetrieveRemotePost
from app.activitypub.util import resolve_remote_post_from_search


@bp.route('/search', methods=['GET', 'POST'])
@limiter.limit("100 per day;20 per 5 minutes", exempt_when=lambda: current_user.is_authenticated)
def run_search():
    if 'bingbot' in request.user_agent.string:  # Stop bingbot from running nonsense searches
        abort(404)
    languages = Language.query.order_by(Language.name).all()
    communities = Community.query.filter(Community.banned == False).order_by(Community.name)
    instance_software = Instance.unique_software_names()
    if current_user.is_authenticated:
        banned_from = communities_banned_from(current_user.id)
        communities = communities.filter(Community.id.not_in(banned_from))
    else:
        banned_from = []

    page = request.args.get('page', 1, type=int)
    community_id = request.args.get('community', 0, type=int)
    language_id = request.args.get('language', 0, type=int)
    type = request.args.get('type', 0, type=int)
    software = request.args.get('software', '')
    low_bandwidth = request.cookies.get('low_bandwidth', '0') == '1'
    q = request.args.get('q')
    sort_by = request.args.get('sort_by', '')

    if q is not None or type != 0 or language_id != 0 or community_id != 0:
        posts = Post.query.filter(Post.deleted == False)
        if current_user.is_authenticated:
            if current_user.ignore_bots == 1:
                posts = posts.filter(Post.from_bot == False)
            if current_user.hide_nsfl == 1:
                posts = posts.filter(Post.nsfl == False)
            if current_user.hide_nsfw == 1:
                posts = posts.filter(Post.nsfw == False)
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
            if banned_from:
                posts = posts.filter(Post.community_id.not_in(banned_from))
        else:
            posts = posts.filter(Post.from_bot == False)
            posts = posts.filter(Post.nsfl == False)
            posts = posts.filter(Post.nsfw == False)

        posts = posts.filter(Post.indexable == True)
        if q is not None:
            posts = posts.search(q, sort=True if sort_by == '' else False)
        if type != 0:
            posts = posts.filter(Post.type == type)
        if community_id:
            posts = posts.filter(Post.community_id == community_id)
        if language_id:
            posts = posts.filter(Post.language_id == language_id)
        if software:
            posts = posts.join(Instance, Post.instance_id == Instance.id).filter(Instance.software == software)
        if sort_by == 'date':
            posts = posts.order_by(desc(Post.posted_at))
        elif sort_by == 'top':
            posts = posts.order_by(desc(Post.up_votes - Post.down_votes))

        posts = posts.paginate(page=page, per_page=100 if current_user.is_authenticated and not low_bandwidth else 50,
                               error_out=False)

        next_url = url_for('search.run_search', page=posts.next_num, q=q) if posts.has_next else None
        prev_url = url_for('search.run_search', page=posts.prev_num, q=q) if posts.has_prev and page != 1 else None

        # Voting history
        if current_user.is_authenticated:
            recently_upvoted = recently_upvoted_posts(current_user.id)
            recently_downvoted = recently_downvoted_posts(current_user.id)
        else:
            recently_upvoted = []
            recently_downvoted = []

        return render_template('search/results.html', title=_('Search results for %(q)s', q=q), posts=posts, q=q,
                               community_id=community_id, language_id=language_id, communities=communities.all(),
                               languages=languages,
                               next_url=next_url, prev_url=prev_url, show_post_community=True,
                               recently_upvoted=recently_upvoted,
                               recently_downvoted=recently_downvoted,
                               moderating_communities=moderating_communities(current_user.get_id()),
                               joined_communities=joined_communities(current_user.get_id()),
                               menu_topics=menu_topics(),
                               site=g.site)

    else:
        return render_template('search/start.html', title=_('Search'), communities=communities.all(),
                               languages=languages, instance_software=instance_software,
                               moderating_communities=moderating_communities(current_user.get_id()),
                               joined_communities=joined_communities(current_user.get_id()),
                               menu_topics=menu_topics(),
                               site=g.site)


@bp.route('/retrieve_remote_post', methods=['GET', 'POST'])
@login_required
def retrieve_remote_post():
    if current_user.banned:
        return show_ban_message()
    form = RetrieveRemotePost()
    new_post = None
    if form.validate_on_submit():
        address = form.address.data.strip()
        new_post = resolve_remote_post_from_search(address)
        if new_post is None:
            flash(_('Post not found.'), 'warning')

    return render_template('community/retrieve_remote_post.html',
                           title=_('Retrieve Remote Post'), form=form, new_post=new_post)
