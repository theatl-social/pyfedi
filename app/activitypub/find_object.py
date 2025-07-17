"""
Utility to find ActivityPub objects by their ap_id.
"""
from app.models import Post, PostReply, Community, Feed, User

def find_object_by_ap_id(ap_id: str):
    """
    Find a Post, PostReply, Community, Feed, or User by their ActivityPub ID.
    Returns the first matching object or None if not found.
    """
    if not ap_id:
        return None
    post = Post.query.filter_by(ap_id=ap_id).first()
    if post:
        return post
    reply = PostReply.query.filter_by(ap_id=ap_id).first()
    if reply:
        return reply
    community = Community.query.filter_by(ap_id=ap_id).first()
    if community:
        return community
    feed = Feed.query.filter_by(ap_id=ap_id).first()
    if feed:
        return feed
    user = User.query.filter_by(ap_id=ap_id).first()
    if user:
        return user
    return None
