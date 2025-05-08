from datetime import timezone
from random import randint

from feedgen.feed import FeedGenerator
from flask import redirect, url_for, flash, request, make_response, session, Markup, current_app, abort, g
from flask_login import login_user, logout_user, current_user, login_required
from flask_babel import _

from app import db, constants, cache, limiter
from app.constants import POST_STATUS_REVIEWING
from app.inoculation import inoculation
from app.models import Post, Domain, Community, DomainBlock, read_posts
from app.domain import bp
from app.utils import render_template, permission_required, joined_communities, moderating_communities, \
    user_filters_posts, blocked_domains, blocked_instances, menu_topics, menu_instance_feeds, menu_my_feeds, \
    menu_subscribed_feeds, recently_upvoted_posts, recently_downvoted_posts, mimetype_from_url, request_etag_matches, \
    return_304, joined_or_modding_communities
from sqlalchemy import desc, or_


@bp.route('/d/<domain_id>', methods=['GET'])
def show_domain(domain_id):
    with limiter.limit('60/minute'):
        page = request.args.get('page', 1, type=int)

        if '.' in domain_id:
            domain = Domain.query.filter_by(name=domain_id, banned=False).first()
        else:
            domain = Domain.query.get_or_404(domain_id)
            if domain.banned:
                domain = None
        if domain:
            if current_user.is_anonymous or current_user.ignore_bots == 1:
                posts = Post.query.join(Community, Community.id == Post.community_id).\
                    filter(Post.from_bot == False, Post.domain_id == domain.id, Community.banned == False, Post.deleted == False, Post.status > POST_STATUS_REVIEWING).\
                    order_by(desc(Post.posted_at))
            else:
                posts = Post.query.join(Community).filter(Post.domain_id == domain.id, Community.banned == False, Post.deleted == False, Post.status > POST_STATUS_REVIEWING).order_by(desc(Post.posted_at))

            if current_user.is_authenticated:
                instance_ids = blocked_instances(current_user.id)
                if instance_ids:
                    posts = posts.filter(or_(Post.instance_id.not_in(instance_ids), Post.instance_id == None))
                content_filters = user_filters_posts(current_user.id)
            else:
                content_filters = {}

            # don't show posts a user has already interacted with
            if current_user.is_authenticated and current_user.hide_read_posts:
                posts = posts.outerjoin(read_posts, (Post.id == read_posts.c.read_post_id) & (read_posts.c.user_id == current_user.id))
                posts = posts.filter(read_posts.c.read_post_id.is_(None))  # Filter where there is no corresponding read post for the current user

            # pagination
            posts = posts.paginate(page=page, per_page=100, error_out=False)
            next_url = url_for('domain.show_domain', domain_id=domain_id, page=posts.next_num) if posts.has_next else None
            prev_url = url_for('domain.show_domain', domain_id=domain_id, page=posts.prev_num) if posts.has_prev and page != 1 else None

            # Voting history
            if current_user.is_authenticated:
                recently_upvoted = recently_upvoted_posts(current_user.id)
                recently_downvoted = recently_downvoted_posts(current_user.id)
            else:
                recently_upvoted = []
                recently_downvoted = []

            return render_template('domain/domain.html', domain=domain, title=domain.name, posts=posts,
                                   POST_TYPE_IMAGE=constants.POST_TYPE_IMAGE, POST_TYPE_LINK=constants.POST_TYPE_LINK,
                                   POST_TYPE_VIDEO=constants.POST_TYPE_VIDEO,
                                   next_url=next_url, prev_url=prev_url,
                                   content_filters=content_filters, recently_upvoted=recently_upvoted, recently_downvoted=recently_downvoted,
                                   site=g.site, joined_communities=joined_or_modding_communities(current_user.get_id()),
                                   rss_feed=f"https://{current_app.config['SERVER_NAME']}/d/{domain.id}/feed" if domain.post_count > 0 else None,
                                   rss_feed_name=f"{domain.name} on {g.site.name}" if domain.post_count > 0 else None,
                                   inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None,
                                   )
        else:
            abort(404)


@bp.route('/d/<domain_id>/feed', methods=['GET'])
def show_domain_rss(domain_id):
    with limiter.limit('60/minute'):
        if '.' in domain_id:
            domain = Domain.query.filter_by(name=domain_id, banned=False).first()
        else:
            domain = Domain.query.get_or_404(domain_id)
            if domain.banned:
                domain = None
        if domain:
            # If nothing has changed since their last visit, return HTTP 304
            current_etag = f"{domain.id}_{hash(domain.post_count)}"
            if request_etag_matches(current_etag):
                return return_304(current_etag, 'application/rss+xml')

            posts = Post.query.join(Community, Community.id == Post.community_id). \
                filter(Post.from_bot == False, Post.domain_id == domain.id, Community.banned == False,
                       Post.deleted == False, Post.status > POST_STATUS_REVIEWING). \
                order_by(desc(Post.posted_at)).limit(100)

            fg = FeedGenerator()
            fg.id(f"https://{current_app.config['SERVER_NAME']}/d/{domain_id}")
            fg.title(f'{domain.name} on {g.site.name}')
            fg.link(href=f"https://{current_app.config['SERVER_NAME']}/d/{domain_id}", rel='alternate')
            fg.logo(f"https://{current_app.config['SERVER_NAME']}/static/images/apple-touch-icon.png")
            fg.subtitle(' ')
            fg.link(href=f"https://{current_app.config['SERVER_NAME']}/c/{domain_id}/feed", rel='self')
            fg.language('en')

            already_added = set()

            for post in posts:
                fe = fg.add_entry()
                fe.title(post.title)
                fe.link(href=f"https://{current_app.config['SERVER_NAME']}/post/{post.id}")
                if post.url:
                    if post.url in already_added:
                        continue
                    type = mimetype_from_url(post.url)
                    if type and not type.startswith('text/'):
                        fe.enclosure(post.url, type=type)
                    already_added.add(post.url)
                fe.description(post.body_html)
                fe.guid(post.profile_id(), permalink=True)
                fe.author(name=post.author.user_name)
                fe.pubDate(post.created_at.replace(tzinfo=timezone.utc))

            response = make_response(fg.rss_str())
            response.headers.set('Content-Type', 'application/rss+xml')
            response.headers.add_header('ETag', f"{domain.id}_{hash(domain.post_count)}")
            response.headers.add_header('Cache-Control', 'no-cache, max-age=600, must-revalidate')
            return response
        else:
            abort(404)


@bp.route('/domains', methods=['GET'])
def domains():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    domains = Domain.query.filter_by(banned=False)
    if search != '':
        domains = domains.filter(Domain.name.ilike(f'%{search}%'))
    domains = domains.order_by(Domain.name)
    domains = domains.paginate(page=page, per_page=100, error_out=False)

    ban_visibility_permission = False

    if not current_user.is_anonymous:
        if not current_user.created_recently() and current_user.reputation > 100 or current_user.is_admin():
            ban_visibility_permission = True

    next_url = url_for('domain.domains', page=domains.next_num) if domains.has_next else None
    prev_url = url_for('domain.domains', page=domains.prev_num) if domains.has_prev and page != 1 else None

    return render_template('domain/domains.html', title='All known domains', domains=domains,
                           next_url=next_url, prev_url=prev_url, search=search, ban_visibility_permission=ban_visibility_permission)


@bp.route('/domains/banned', methods=['GET'])
@login_required
def domains_blocked_list():
    if not current_user.trustworthy():
        abort(404)

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    domains = Domain.query.filter_by(banned=True)
    if search != '':
        domains = domains.filter(Domain.name.ilike(f'%{search}%'))
    domains = domains.order_by(Domain.name)
    domains = domains.paginate(page=page, per_page=100, error_out=False)

    next_url = url_for('domain.domains', page=domains.next_num) if domains.has_next else None
    prev_url = url_for('domain.domains', page=domains.prev_num) if domains.has_prev and page != 1 else None

    return render_template('domain/domains_blocked.html', title='Domains blocked on this instance', domains=domains,
                           next_url=next_url, prev_url=prev_url, search=search)


@bp.route('/d/<int:domain_id>/block')
@login_required
def domain_block(domain_id):
    domain = Domain.query.get_or_404(domain_id)
    block = DomainBlock.query.filter_by(user_id=current_user.id, domain_id=domain_id).first()
    if not block:
        block = DomainBlock(user_id=current_user.id, domain_id=domain_id)
        db.session.add(block)
        db.session.commit()
    cache.delete_memoized(blocked_domains, current_user.id)
    flash(_('%(name)s blocked.', name=domain.name))
    return redirect(url_for('domain.show_domain', domain_id=domain.id))


@bp.route('/d/<int:domain_id>/unblock')
@login_required
def domain_unblock(domain_id):
    domain = Domain.query.get_or_404(domain_id)
    block = DomainBlock.query.filter_by(user_id=current_user.id, domain_id=domain_id).first()
    if block:
        db.session.delete(block)
        db.session.commit()
    cache.delete_memoized(blocked_domains, current_user.id)
    flash(_('%(name)s un-blocked.', name=domain.name))
    return redirect(url_for('domain.show_domain', domain_id=domain.id))


@bp.route('/d/<int:domain_id>/ban')
@login_required
@permission_required('manage users')
def domain_ban(domain_id):
    domain = Domain.query.get_or_404(domain_id)
    if domain:
        domain.banned = True
        db.session.commit()
        domain.purge_content()
        flash(_('%(name)s banned for all users and all content deleted.', name=domain.name))
        return redirect(url_for('domain.domains'))


@bp.route('/d/<int:domain_id>/unban')
@login_required
@permission_required('manage users')
def domain_unban(domain_id):
    domain = Domain.query.get_or_404(domain_id)
    if domain:
        domain.banned = False
        db.session.commit()
        flash(_('%(name)s un-banned for all users.', name=domain.name))
        return redirect(url_for('domain.show_domain', domain_id=domain.id))
