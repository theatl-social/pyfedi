from datetime import timezone
from random import randint

import flask
from feedgen.feed import FeedGenerator
from flask import redirect, url_for, flash, request, make_response, current_app, abort, g
from flask_babel import _
from flask_login import current_user
from sqlalchemy import desc, or_

from app import db, constants
from app.constants import POST_STATUS_REVIEWING
from app.inoculation import inoculation
from app.models import Post, Community, Tag, post_tag
from app.tag import bp
from app.utils import render_template, permission_required, user_filters_posts, blocked_instances, blocked_users, \
    blocked_domains, mimetype_from_url, \
    blocked_communities, login_required, moderating_communities_ids


@bp.route('/tag/<tag>', methods=['GET'])
def show_tag(tag):
    page = request.args.get('page', 1, type=int)

    tag = Tag.query.filter(Tag.name == tag.lower()).first()
    if tag:

        posts = Post.query.join(Community, Community.id == Post.community_id). \
            join(post_tag, post_tag.c.post_id == Post.id).filter(post_tag.c.tag_id == tag.id). \
            filter(Community.banned == False, Post.deleted == False, Post.status > POST_STATUS_REVIEWING)

        if current_user.is_anonymous or current_user.ignore_bots == 1:
            posts = posts.filter(Post.from_bot == False)

        if current_user.is_authenticated:
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
            content_filters = user_filters_posts(current_user.id)
        else:
            content_filters = {}

        posts = posts.order_by(desc(Post.posted_at))

        # pagination
        posts = posts.paginate(page=page, per_page=100, error_out=False)
        next_url = url_for('tag.show_tag', tag=tag, page=posts.next_num) if posts.has_next else None
        prev_url = url_for('tag.show_tag', tag=tag, page=posts.prev_num) if posts.has_prev and page != 1 else None

        return render_template('tag/tag.html', tag=tag, title=tag.name, posts=posts,
                               POST_TYPE_IMAGE=constants.POST_TYPE_IMAGE, POST_TYPE_LINK=constants.POST_TYPE_LINK,
                               POST_TYPE_VIDEO=constants.POST_TYPE_VIDEO,
                               next_url=next_url, prev_url=prev_url,
                               content_filters=content_filters,
                               moderated_community_ids=moderating_communities_ids(current_user.get_id()),
                               rss_feed=f"https://{current_app.config['SERVER_NAME']}/tag/{tag.name}/feed",
                               rss_feed_name=f"#{tag.display_as} on {g.site.name}",
                               inoculation=inoculation[randint(0, len(inoculation) - 1)] if g.site.show_inoculation_block else None,
                               )
    else:
        abort(404)


@bp.route('/tag/<tag>/feed', methods=['GET'])
def show_tag_rss(tag):
    tag = Tag.query.filter(Tag.name == tag.lower()).first()
    if tag:
        posts = Post.query.join(Community, Community.id == Post.community_id). \
            join(post_tag, post_tag.c.post_id == Post.id).filter(post_tag.c.tag_id == tag.id). \
            filter(Community.banned == False, Post.deleted == False, Post.status > POST_STATUS_REVIEWING)

        if current_user.is_anonymous or current_user.ignore_bots == 1:
            posts = posts.filter(Post.from_bot == False)
        posts = posts.order_by(desc(Post.posted_at)).limit(20).all()

        description = None
        og_image = None
        fg = FeedGenerator()
        fg.id(f"https://{current_app.config['SERVER_NAME']}/tag/{tag.name}")
        fg.title(f'#{tag.display_as} on {g.site.name}')
        fg.link(href=f"https://{current_app.config['SERVER_NAME']}/tag/{tag.name}", rel='alternate')
        if og_image:
            fg.logo(og_image)
        else:
            fg.logo(f"https://{current_app.config['SERVER_NAME']}{g.site.logo_152 if g.site.logo_152 else '/static/images/apple-touch-icon.png'}")
        if description:
            fg.subtitle(description)
        else:
            fg.subtitle(' ')
        fg.link(href=f"https://{current_app.config['SERVER_NAME']}/tag/{tag.name}/feed", rel='self')
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
        return response
    else:
        abort(404)


@bp.route('/tags', methods=['GET'])
def tags():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    tags = Tag.query.filter_by(banned=False)
    if search != '':
        tags = tags.filter(Tag.name.ilike(f'%{search}%'))
    tags = tags.order_by(Tag.name)
    tags = tags.paginate(page=page, per_page=100, error_out=False)

    ban_visibility_permission = False

    if current_user.is_authenticated and current_user.is_admin_or_staff():
        ban_visibility_permission = True

    next_url = url_for('tag.tags', page=tags.next_num) if tags.has_next else None
    prev_url = url_for('tag.tags', page=tags.prev_num) if tags.has_prev and page != 1 else None

    return render_template('tag/tags.html', title='All known tags', tags=tags,
                           next_url=next_url, prev_url=prev_url, search=search,
                           ban_visibility_permission=ban_visibility_permission)


@bp.route('/tags/banned', methods=['GET'])
@login_required
def tags_blocked_list():
    if not current_user.trustworthy():
        abort(404)

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    tags = Tag.query.filter_by(banned=True)
    if search != '':
        tags = tags.filter(Tag.name.ilike(f'%{search}%'))
    tags = tags.order_by(Tag.name)
    tags = tags.paginate(page=page, per_page=100, error_out=False)

    next_url = url_for('tag.tags', page=tags.next_num) if tags.has_next else None
    prev_url = url_for('tag.tags', page=tags.prev_num) if tags.has_prev and page != 1 else None

    return render_template('tag/tags_blocked.html', title='Tags blocked on this instance', tags=tags,
                           next_url=next_url, prev_url=prev_url, search=search)


@bp.route('/tag/<tag>/ban', methods=['POST'])
@login_required
@permission_required('manage users')
def tag_ban(tag):
    tag = Tag.query.filter(Tag.name == tag.lower()).first()
    if tag:
        tag.banned = True
        db.session.commit()
        # tag.purge_content()
        flash(_('%(name)s banned for all users and all content deleted.', name=tag.name))
        return redirect(url_for('tag.tags'))


@bp.route('/tag/<tag>/unban', methods=['POST'])
@login_required
@permission_required('manage users')
def tag_unban(tag):
    tag = Tag.query.filter(Tag.name == tag.lower()).first()
    if tag:
        tag.banned = False
        db.session.commit()
        flash(_('%(name)s un-banned for all users.', name=tag.name))
        return redirect(url_for('tag.show_tag', tag=tag.name))


@bp.route('/tags/community/<community_id>', methods=['GET'])
def tags_community(community_id: int):
    try:
        community = Community.query.filter_by(id=community_id).one()
    except Exception:
        abort(404)

    # Get tags with post counts
    tags_query = db.session.query(Tag, db.func.count(Post.id).label('num_posts')). \
        filter(Tag.banned == False). \
        join(post_tag, post_tag.c.tag_id == Tag.id). \
        join(Post, Post.id == post_tag.c.post_id). \
        filter(Post.community_id == community_id, Post.deleted == False). \
        group_by(Tag.id)
    
    # Limit to top 50 tags by usage for performance
    tag_results = tags_query.order_by(db.desc('num_posts')).limit(50).all()
    
    # Prepare tag data for JavaScript
    tags_data = []
    tag_ids = []
    for tag, num_posts in tag_results:
        tags_data.append({
            'id': tag.id,
            'text': tag.name,
            'numPosts': num_posts
        })
        tag_ids.append(tag.id)
    
    # Calculate tag relationships (co-occurrence in posts)
    relationships = {}
    if tag_ids:
        # Simpler approach: find all posts with multiple tags and count co-occurrences
        for tag1_id in tag_ids:
            # Find posts that contain this tag
            posts_with_tag1 = db.session.query(post_tag.c.post_id).filter(
                post_tag.c.tag_id == tag1_id
            ).join(Post, Post.id == post_tag.c.post_id).filter(
                Post.community_id == community_id,
                Post.deleted == False
            ).subquery()
            
            # Find other tags that appear in the same posts
            cooccurrence_counts = db.session.query(
                post_tag.c.tag_id.label('tag2_id'),
                db.func.count().label('count')
            ).filter(
                post_tag.c.post_id.in_(db.select(posts_with_tag1.c.post_id)),
                post_tag.c.tag_id.in_(tag_ids),
                post_tag.c.tag_id != tag1_id
            ).group_by(post_tag.c.tag_id).all()
            
            if cooccurrence_counts:
                relationships[tag1_id] = {
                    tag2_id: count for tag2_id, count in cooccurrence_counts
                }

    return render_template('tag/tags_community.html', title='Community tags',
                           community=community, tags_data=tags_data, 
                           tag_relationships=relationships)


@bp.route('/tags/posts/<int:tag_id>')
def tag_posts(tag_id):
    posts = Post.query.join(Community, Community.id == Post.community_id). \
        join(post_tag, post_tag.c.post_id == Post.id).filter(post_tag.c.tag_id == tag_id). \
        filter(Community.banned == False, Post.deleted == False, Post.status > POST_STATUS_REVIEWING)

    if current_user.is_anonymous or current_user.ignore_bots == 1:
        posts = posts.filter(Post.from_bot == False)
    posts = posts.order_by(desc(Post.posted_at)).limit(20).all()

    return flask.render_template('tag/tag_posts.html', posts=posts)
