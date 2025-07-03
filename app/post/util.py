from typing import List
from urllib.parse import urlparse

from flask_login import current_user
from sqlalchemy import desc, asc, text, or_

from app import db
from app.constants import POST_TYPE_LINK, POST_TYPE_IMAGE, POST_TYPE_VIDEO, POST_TYPE_POLL
from app.models import PostReply, Post, Community, User
from app.utils import blocked_instances, blocked_users, is_video_hosting_site


# replies to a post, in a tree, sorted by a variety of methods
def post_replies(community: Community, post_id: int, sort_by: str, viewer: User) -> List[PostReply]:
    comments = PostReply.query.filter_by(post_id=post_id)
    if viewer.is_authenticated:
        instance_ids = blocked_instances(viewer.id)
        if instance_ids:
            comments = comments.filter(or_(PostReply.instance_id.not_in(instance_ids), PostReply.instance_id == None))
        if viewer.ignore_bots == 1:
            comments = comments.filter(PostReply.from_bot == False)
        blocked_accounts = blocked_users(viewer.id)
        if blocked_accounts:
            comments = comments.filter(PostReply.user_id.not_in(blocked_accounts))
        if viewer.reply_hide_threshold and not (viewer.is_admin() or community.is_owner() or community.is_moderator()):
            comments = comments.filter(PostReply.score > viewer.reply_hide_threshold)
        if viewer.read_language_ids and len(viewer.read_language_ids) > 0:
            comments = comments.filter(
                or_(PostReply.language_id.in_(tuple(viewer.read_language_ids)), PostReply.language_id == None))
    else:
        comments.filter(PostReply.score > -20)

    if sort_by == 'hot':
        comments = comments.order_by(desc(PostReply.ranking))
    elif sort_by == 'top':
        comments = comments.order_by(desc(PostReply.score))
    elif sort_by == 'new':
        comments = comments.order_by(desc(PostReply.posted_at))
    elif sort_by == 'old':
        comments = comments.order_by(asc(PostReply.posted_at))

    comments = comments.limit(2000)  # paginating indented replies is too hard so just get the first 2000.

    comments_dict = {comment.id: {'comment': comment, 'replies': []} for comment in comments.all()}

    for comment in comments:
        if comment.parent_id is not None:
            parent_comment = comments_dict.get(comment.parent_id)
            if parent_comment:
                parent_comment['replies'].append(comments_dict[comment.id])

    return [comment for comment in comments_dict.values() if comment['comment'].parent_id is None]


def get_comment_branch(post_id: int, comment_id: int, sort_by: str) -> List[PostReply]:
    # Fetch the specified parent comment and its replies
    parent_comment = PostReply.query.get(comment_id)
    if parent_comment is None:
        return []

    comments = PostReply.query.filter(PostReply.post_id == post_id)
    if current_user.is_authenticated:
        instance_ids = blocked_instances(current_user.id)
        if instance_ids:
            comments = comments.filter(or_(PostReply.instance_id.not_in(instance_ids), PostReply.instance_id == None))
    if sort_by == 'hot':
        comments = comments.order_by(desc(PostReply.ranking))
    elif sort_by == 'top':
        comments = comments.order_by(desc(PostReply.score))
    elif sort_by == 'new':
        comments = comments.order_by(desc(PostReply.posted_at))

    comments_dict = {comment.id: {'comment': comment, 'replies': []} for comment in comments.all()}

    for comment in comments:
        if comment.parent_id is not None:
            parent_comment = comments_dict.get(comment.parent_id)
            if parent_comment:
                parent_comment['replies'].append(comments_dict[comment.id])

    return [comment for comment in comments_dict.values() if comment['comment'].id == comment_id]


# The number of replies a post has
def get_post_reply_count(post_id) -> int:
    return db.session.execute(
        text('SELECT COUNT(id) as c FROM "post_reply" WHERE post_id = :post_id AND deleted is false'),
        {'post_id': post_id}).scalar()


def tags_to_string(post: Post) -> str:
    if len(post.tags) > 0:
        return ', '.join([tag.display_as for tag in post.tags])


def body_has_no_archive_link(body):
    if body:
        return 'https://archive.' not in body and 'https://12ft.io' not in body
    else:
        return True


def url_needs_archive(url) -> bool:
    paywalled_sites = ['washingtonpost.com', 'nytimes.com', 'wsj.com', 'economist.com', 'ft.com', 'telegraph.co.uk',
                       'bild.de', 'theatlantic.com', 'lemonde.fr', 'nzherald.co.nz']
    if url:
        try:
            parsed_url = urlparse(url.replace('www.', ''))
            hostname = parsed_url.hostname.lower()
        except:
            return False
        if hostname == 'nytimes.com' and 'unlocked_article_code' in url:
            return False
        if hostname == 'theatlantic.com' and 'gift' in url:
            return False
        return hostname in paywalled_sites
    else:
        return False


def generate_archive_link(url) -> bool:
    return 'https://archive.ph/' + url


# Forms like the cross post form need the type for the url
def post_type_to_form_url_type(post_type: int, post_url: str):
    if post_type == POST_TYPE_LINK or is_video_hosting_site(post_url):
        return 'link'
    elif post_type == POST_TYPE_IMAGE:
        return 'image'
    elif post_type == POST_TYPE_VIDEO:
        return 'video'
    elif post_type == POST_TYPE_POLL:
        return 'poll'
    else:
        return ''
