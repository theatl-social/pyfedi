"""
find_object.py

Utility functions for finding ActivityPub objects locally or remotely.
"""

from app.models import Post, PostReply
from app.activitypub.util import resolve_remote_post

def find_object(ap_id):
    """
    Attempts to find an ActivityPub object (Post or PostReply) locally.
    If not found, attempts to fetch it remotely and returns the result if successful.
    Returns None if the object cannot be found or fetched.
    """
    obj = Post.get_by_ap_id(ap_id)
    if obj:
        return obj
    obj = PostReply.get_by_ap_id(ap_id)
    if obj:
        return obj
    # Try to fetch remotely
    try:
        resolve_remote_post(ap_id)
    except Exception:
        pass
    # Try again locally after remote fetch
    obj = Post.get_by_ap_id(ap_id)
    if obj:
        return obj
    obj = PostReply.get_by_ap_id(ap_id)
    if obj:
        return obj
    return None
