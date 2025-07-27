"""
Activity and Feed endpoints for ActivityPub

This module handles individual activity lookups and feed-related
ActivityPub endpoints.

Endpoints:
    - /activities/<type>/<id> - Individual activity lookup
    - /activity_result/<id> - Activity result pages
    - /f/<actor> - Feed actor endpoints
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Union
from flask import abort, redirect, url_for, request, current_app, jsonify
import json
from datetime import datetime

from app import db, cache
from app.activitypub.routes import bp
from app.activitypub.routes.helpers import make_activitypub_response
from app.models import Feed, FeedMember, Post, ActivityPubLog, FeedItem
from app.utils import is_activitypub_request
from app.constants import APLOG_DUPLICATE, APLOG_IGNORED, APLOG_FAILURE, APLOG_SUCCESS, APLOG_CREATE

# Type aliases
type ActivityType = str
type ActivityId = str
type FeedName = str


@bp.route('/activities/<type>/<id>')
@cache.cached(timeout=600)
def activity_view(type: ActivityType, id: ActivityId) -> tuple[Dict[str, Any], int]:
    """
    View an individual activity by type and ID.
    
    This endpoint allows looking up activities that have been
    created by this instance from the ActivityPubLog table.
    
    Args:
        type: Activity type (create, update, delete, etc.)
        id: Activity ID
        
    Returns:
        ActivityPub activity object
        
    Raises:
        404: If activity not found
    """
    # Build the full activity ID
    activity_id = f"https://{current_app.config['SERVER_NAME']}/activities/{type}/{id}"
    
    # Look up the activity in the log
    activity = ActivityPubLog.query.filter_by(
        activity_id=activity_id
    ).first()
    
    if activity:
        if activity.activity_json is not None:
            activity_json = json.loads(activity.activity_json)
        else:
            activity_json = {}
        
        resp = jsonify(activity_json)
        resp.content_type = 'application/activity+json'
        return resp
    else:
        abort(404)


@bp.route('/activity_result/<path:id>')
def activity_result(id: str) -> Union[str, tuple[Dict[str, Any], int]]:
    """
    View the result of an activity.
    
    Other instances can query the result of their POST to the inbox
    by using this endpoint. The ID of the activity they sent (minus
    the https:// on the front) is the id parameter.
    
    Example: https://piefed.ngrok.app/activity_result/piefed.ngrok.app/activities/announce/EfjyZ3BE5SzQK0C
    
    Args:
        id: Activity result ID (path after https://)
        
    Returns:
        Redirect to result or JSON response
    """
    # Reconstruct the full activity ID
    activity_id = f"https://{id}"
    
    # Look up the activity
    activity = ActivityPubLog.query.filter_by(
        activity_id=activity_id
    ).first()
    
    if activity:
        if activity.result == APLOG_DUPLICATE:
            return jsonify({'status': 'duplicate'})
        elif activity.result == APLOG_IGNORED:
            return jsonify({'status': 'ignored'})
        elif activity.result == APLOG_FAILURE:
            return jsonify({'status': 'failure', 'message': activity.exception_message})
        elif activity.result == APLOG_SUCCESS:
            # Try to find what was created
            if activity.activity_type == APLOG_CREATE:
                # Look for a post or comment that was created
                from app.models import Post, PostReply
                
                # Check if it's a post
                post = Post.query.filter_by(
                    ap_id=activity.activity_object
                ).first()
                if post:
                    return redirect(url_for('post.show_post', post_id=post.id))
                
                # Check if it's a comment
                comment = PostReply.query.filter_by(
                    ap_id=activity.activity_object
                ).first()
                if comment:
                    return redirect(url_for('post.show_post', post_id=comment.post_id))
            
            return jsonify({'status': 'success'})
    
    # Activity not found
    return jsonify({'status': 'not_found'}), 404


@bp.route('/f/<actor>')
@bp.route('/f/<actor>/<feed_owner>', methods=['GET'])
def feed_actor(actor: FeedName, feed_owner: Optional[str] = None) -> Union[str, tuple[Dict[str, Any], int]]:
    """
    Feed actor endpoint.
    
    Feeds are a PyFedi-specific extension that allows curated
    collections of content from multiple sources.
    
    Args:
        actor: Feed name
        feed_owner: Optional feed owner parameter
        
    Returns:
        ActivityPub Service actor or HTML redirect
    """
    actor = actor.strip()
    
    if feed_owner is not None:
        # Handle the feed_owner case
        feed = Feed.query.filter_by(name=actor).first()
        if not feed:
            abort(404)
        
        # Verify the owner matches
        if feed.user.user_name != feed_owner:
            abort(404)
        
        # Return owner information
        owner_info = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"https://{current_app.config['SERVER_NAME']}/f/{actor}/{feed_owner}",
            "type": "Person",
            "name": feed.user.display_name,
            "url": feed.user.public_url()
        }
        
        return make_activitypub_response(owner_info)
    
    # Regular feed actor request
    feed = Feed.query.filter_by(name=actor).first()
    if not feed:
        abort(404)
    
    # If not an ActivityPub request, redirect to HTML view
    if not is_activitypub_request(request):
        return redirect(url_for('feed.show_feed', actor=actor))
    
    # Build Service actor for feed
    actor_data = _build_feed_actor_object(feed)
    
    return make_activitypub_response(actor_data)




@bp.route('/f/<actor>/inbox', methods=['POST'])
def feed_inbox(actor: FeedName) -> tuple[str, int]:
    """
    Feed inbox endpoint.
    
    Receives activities directed at feeds.
    
    Args:
        actor: Feed name
        
    Returns:
        204 No Content on success
    """
    feed = Feed.query.filter_by(name=actor).first()
    if not feed:
        abort(404)
    
    # Process the activity
    # For now, feeds don't process incoming activities
    
    return '', 204


@bp.route('/f/<actor>/outbox', methods=['GET'])
def feed_outbox(actor: FeedName) -> tuple[Dict[str, Any], int]:
    """
    Feed outbox endpoint.
    
    Lists activities from the feed.
    
    Args:
        actor: Feed name
        
    Returns:
        ActivityPub OrderedCollection
    """
    feed = Feed.query.filter_by(name=actor).first()
    if not feed:
        abort(404)
    
    # Get recent posts from feed
    from app.models import FeedItem
    feed_items = FeedItem.query.filter_by(
        feed_id=feed.id
    ).order_by(FeedItem.created_at.desc()).limit(50).all()
    
    # Convert to activities
    items = []
    for item in feed_items:
        if item.post and not item.post.deleted:
            from app.activitypub.util import post_to_activity
            activity = post_to_activity(item.post, item.post.community)
            items.append(activity)
    
    collection = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://{current_app.config['SERVER_NAME']}/f/{actor}/outbox",
        "type": "OrderedCollection",
        "totalItems": len(items),
        "orderedItems": items
    }
    
    return make_activitypub_response(collection)


@bp.route('/f/<actor>/following', methods=['GET'])
def feed_following(actor: FeedName) -> tuple[Dict[str, Any], int]:
    """
    Feed following collection.
    
    Lists what the feed follows (communities, users, etc).
    
    Args:
        actor: Feed name
        
    Returns:
        ActivityPub Collection
    """
    feed = Feed.query.filter_by(name=actor).first()
    if not feed:
        abort(404)
    
    # Get followed entities
    # This would include communities and users the feed aggregates
    following = []
    
    collection = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://{current_app.config['SERVER_NAME']}/f/{actor}/following",
        "type": "Collection",
        "totalItems": len(following),
        "items": following
    }
    
    return make_activitypub_response(collection)


@bp.route('/f/<actor>/moderators', methods=['GET'])
def feed_moderators(actor: FeedName) -> tuple[Dict[str, Any], int]:
    """
    Feed moderators collection.
    
    Lists users who can moderate the feed.
    
    Args:
        actor: Feed name
        
    Returns:
        ActivityPub Collection
    """
    feed = Feed.query.filter_by(name=actor).first()
    if not feed:
        abort(404)
    
    # Feed owner is the moderator
    moderators = [feed.user.public_url()]
    
    collection = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://{current_app.config['SERVER_NAME']}/f/{actor}/moderators",
        "type": "OrderedCollection",
        "totalItems": len(moderators),
        "orderedItems": moderators
    }
    
    return make_activitypub_response(collection)


@bp.route('/f/<actor>/followers', methods=['GET'])
def feed_followers(actor: FeedName) -> tuple[Dict[str, Any], int]:
    """
    Feed followers collection.
    
    Lists users following this feed.
    
    Args:
        actor: Feed name
        
    Returns:
        ActivityPub Collection with count only
    """
    feed = Feed.query.filter_by(name=actor).first()
    if not feed:
        abort(404)
    
    # Get follower count
    follower_count = FeedMember.query.filter_by(
        feed_id=feed.id
    ).count()
    
    collection = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://{current_app.config['SERVER_NAME']}/f/{actor}/followers",
        "type": "Collection",
        "totalItems": follower_count,
        "items": None  # Privacy
    }
    
    return make_activitypub_response(collection)


def _build_feed_actor_object(feed: Feed) -> Dict[str, Any]:
    """
    Build ActivityPub Service actor for a feed.
    
    Args:
        feed: Feed object
        
    Returns:
        Service actor object
    """
    server_name = current_app.config['SERVER_NAME']
    actor_url = f"https://{server_name}/f/{feed.name}"
    
    actor = {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://w3id.org/security/v1"
        ],
        "id": actor_url,
        "type": "Service",
        "preferredUsername": feed.name,
        "name": feed.title or feed.name,
        "summary": feed.description,
        "inbox": f"{actor_url}/inbox",
        "outbox": f"{actor_url}/outbox",
        "followers": f"{actor_url}/followers",
        "following": f"{actor_url}/following",
        "moderators": f"{actor_url}/moderators",
        "url": actor_url,
        "manuallyApprovesFollowers": False,
        "discoverable": True,
        "published": feed.created_at.isoformat() + 'Z' if feed.created_at else None,
        "attributedTo": feed.user.public_url()
    }
    
    return actor