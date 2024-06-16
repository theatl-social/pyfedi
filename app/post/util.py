from typing import List
from urllib.parse import urlparse

from flask_login import current_user
from sqlalchemy import desc, text, or_

from app import db
from app.models import PostReply, Post
from app.utils import blocked_instances, blocked_users


# replies to a post, in a tree, sorted by a variety of methods
def post_replies(post_id: int, sort_by: str, show_first: int = 0) -> List[PostReply]:
    comments = PostReply.query.filter_by(post_id=post_id).filter(PostReply.deleted == False)
    if current_user.is_authenticated:
        instance_ids = blocked_instances(current_user.id)
        if instance_ids:
            comments = comments.filter(or_(PostReply.instance_id.not_in(instance_ids), PostReply.instance_id == None))
        if current_user.ignore_bots:
            comments = comments.filter(PostReply.from_bot == False)
        blocked_accounts = blocked_users(current_user.id)
        if blocked_accounts:
            comments = comments.filter(PostReply.user_id.not_in(blocked_accounts))
    if sort_by == 'hot':
        comments = comments.order_by(desc(PostReply.ranking))
    elif sort_by == 'top':
        comments = comments.order_by(desc(PostReply.score))
    elif sort_by == 'new':
        comments = comments.order_by(desc(PostReply.posted_at))

    comments = comments.limit(2000) # paginating indented replies is too hard so just get the first 2000.

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

    comments = PostReply.query.filter(PostReply.post_id == post_id, PostReply.deleted == False)
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
def post_reply_count(post_id) -> int:
    return db.session.execute(text('SELECT COUNT(id) as c FROM "post_reply" WHERE post_id = :post_id AND deleted is false'),
                              {'post_id': post_id}).scalar()


def tags_to_string(post: Post) -> str:
    if post.tags.count() > 0:
        return ', '.join([tag.name for tag in post.tags])


def url_has_paywall(url) -> bool:
    paywalled_sites = ['washingtonpost.com', 'wapo.st', 'nytimes.com', 'wsj.com', 'economist.com', 'ft.com', 'telegraph.co.uk',
                       'bild.de', 'theatlantic.com', 'lemonde.fr']
    if url:
        try:
            parsed_url = urlparse(url.replace('www.', ''))
            hostname = parsed_url.hostname.lower()
        except:
            return False
        return hostname in paywalled_sites
    else:
        return False


def generate_paywall_bypass_link(url) -> bool:
    url_without_protocol = url.replace('https://', '').replace('http://', '')
    return 'https://archive.ph/' + url
