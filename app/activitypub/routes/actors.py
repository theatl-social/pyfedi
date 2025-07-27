"""
Actor profile and collection endpoints

This module handles ActivityPub actor profiles (users and communities)
and their collections (outbox, followers, following, etc.).

Maintains compatibility with PyFedi, Lemmy, Mastodon, and other
ActivityPub implementations.

Endpoints:
    - /u/<actor> - User profiles
    - /u/<actor>/outbox - User activity outbox
    - /c/<actor> - Community profiles
    - /c/<actor>/outbox - Community activity outbox
    - /c/<actor>/followers - Community followers collection
    - /c/<actor>/moderators - Community moderators collection
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List, TypedDict, Union, Literal
from flask import request, abort, g, current_app, redirect, url_for
from sqlalchemy import desc

from app import db, cache
from app.activitypub.routes import bp
from app.activitypub.signature import HttpSignature, VerificationError
from app.activitypub.util import public_key, community_members
from app.models import User, Community, CommunityMember, Post, utcnow
from app.utils import (
    is_activitypub_request, get_setting, community_membership,
    ap_datetime, awaken_dormant_instance
)
from app.activitypub.routes.helpers import make_activitypub_response

# Type definitions
type ActorName = str
type ActorUrl = str
type CollectionPage = int


class ActorObject(TypedDict):
    """ActivityPub Actor object"""
    id: str
    type: Literal["Person", "Group", "Service", "Application"]
    inbox: str
    outbox: str
    preferredUsername: str
    name: Optional[str]
    summary: Optional[str]
    url: Optional[str]
    manuallyApprovesFollowers: bool
    discoverable: bool
    publicKey: Dict[str, str]
    endpoints: Dict[str, str]
    icon: Optional[Dict[str, str]]
    image: Optional[Dict[str, str]]
    published: Optional[str]
    updated: Optional[str]
    followers: Optional[str]
    following: Optional[str]
    liked: Optional[str]
    # Group-specific fields
    moderators: Optional[str]
    postingRestrictedToMods: Optional[bool]
    sensitive: Optional[bool]


class Collection(TypedDict):
    """ActivityPub Collection"""
    id: str
    type: Literal["Collection", "OrderedCollection"]
    totalItems: int
    items: Optional[List[Any]]
    first: Optional[str]
    last: Optional[str]


class CollectionPage(TypedDict):
    """ActivityPub Collection Page"""
    id: str
    type: Literal["CollectionPage", "OrderedCollectionPage"]
    totalItems: int
    partOf: str
    items: List[Any]
    next: Optional[str]
    prev: Optional[str]


@bp.route('/u/<actor>', methods=['GET', 'HEAD'])
def user_profile(actor: ActorName) -> Union[str, tuple[Dict[str, Any], int]]:
    """
    User profile endpoint returning ActivityPub actor object.
    
    Args:
        actor: Username to look up
        
    Returns:
        ActivityPub Person object or HTML redirect for browsers
        
    Example:
        GET /u/alice
        Accept: application/activity+json
        
        Returns:
        {
            "@context": [...],
            "id": "https://example.com/u/alice",
            "type": "Person",
            "preferredUsername": "alice",
            "inbox": "https://example.com/u/alice/inbox",
            ...
        }
    """
    if '@' in actor:
        user = User.query.filter_by(email=actor, deleted=False, banned=False, verified=True).first()
    else:
        user = User.query.filter_by(
            user_name=actor, deleted=False, banned=False,
            ap_id=None  # Local users only
        ).first()
    
    if user is None:
        user = User.query.filter_by(
            ap_profile_id=f"https://{current_app.config['SERVER_NAME']}/u/{actor}",
            deleted=False, banned=False
        ).first()
    
    if user is None:
        abort(404)
    
    # If not an ActivityPub request, redirect to HTML profile
    if not is_activitypub_request(request):
        return redirect(url_for('user.show_profile', actor=actor))
    
    # Verify HTTP signature if provided
    if 'Signature' in request.headers:
        try:
            HttpSignature.verify_request(
                request,
                user.public_key if user.public_key else public_key(),
                skip_date=True
            )
            g.verified_signature = True
        except VerificationError:
            g.verified_signature = False
    
    # Build actor object
    actor_data = _build_user_actor_object(user)
    
    return make_activitypub_response(actor_data)


@bp.route('/u/<actor>/outbox', methods=['GET'])
def user_outbox(actor: ActorName) -> tuple[Dict[str, Any], int]:
    """
    User outbox endpoint listing user's public activities.
    
    Currently returns an empty collection as user activities
    are not implemented in PyFedi.
    
    Args:
        actor: Username
        
    Returns:
        ActivityPub OrderedCollection
    """
    user = User.query.filter_by(user_name=actor, deleted=False, banned=False).first()
    if not user:
        abort(404)
    
    outbox = Collection(
        id=f"https://{current_app.config['SERVER_NAME']}/u/{actor}/outbox",
        type="OrderedCollection",
        totalItems=0,
        items=[]
    )
    
    return make_activitypub_response(outbox)


@bp.route('/c/<actor>', methods=['GET'])
def community_profile(actor: ActorName) -> Union[str, tuple[Dict[str, Any], int]]:
    """
    Community profile endpoint returning ActivityPub Group actor.
    
    Handles both local and remote community lookups with full
    compatibility for different ActivityPub implementations.
    
    Args:
        actor: Community name to look up
        
    Returns:
        ActivityPub Group object or HTML redirect for browsers
        
    Example:
        GET /c/technology
        Accept: application/activity+json
        
        Returns:
        {
            "@context": [...],
            "id": "https://example.com/c/technology",
            "type": "Group",
            "preferredUsername": "technology",
            "name": "Technology",
            "inbox": "https://example.com/c/technology/inbox",
            "outbox": "https://example.com/c/technology/outbox",
            "followers": "https://example.com/c/technology/followers",
            "moderators": "https://example.com/c/technology/moderators",
            ...
        }
    """
    if '@' in actor:
        # Handle remote community references
        community = Community.query.filter_by(
            ap_profile_id=actor, banned=False
        ).first()
    else:
        # Local community lookup
        community = Community.query.filter_by(
            name=actor, banned=False, ap_id=None
        ).first()
    
    if community is None:
        # Try alternate lookup methods
        community = Community.query.filter_by(
            ap_profile_id=f"https://{current_app.config['SERVER_NAME']}/c/{actor}",
            banned=False
        ).first()
    
    if community is None:
        abort(404)
    
    # Awaken dormant instance if needed
    if community.instance and community.instance.dormant:
        awaken_dormant_instance(community.instance)
    
    # If not an ActivityPub request, redirect to HTML view
    if not is_activitypub_request(request):
        return redirect(url_for('community.show_community', actor=actor))
    
    # Build Group actor object
    actor_data = _build_community_actor_object(community)
    
    return make_activitypub_response(actor_data)


@bp.route('/c/<actor>/outbox', methods=['GET'])
@cache.cached(timeout=60)
def community_outbox(actor: ActorName, page: Optional[int] = None) -> tuple[Dict[str, Any], int]:
    """
    Community outbox endpoint listing recent posts.
    
    Implements pagination for large collections. Each page contains
    up to 50 posts ordered by creation date.
    
    Args:
        actor: Community name
        page: Optional page number (1-based)
        
    Returns:
        ActivityPub OrderedCollection or OrderedCollectionPage
    """
    community = Community.query.filter_by(name=actor, banned=False).first()
    if not community:
        abort(404)
    
    # Get page parameter
    page_num = request.args.get('page', type=int)
    
    # Base collection URL
    outbox_url = f"https://{current_app.config['SERVER_NAME']}/c/{actor}/outbox"
    
    # Get total post count
    total_posts = Post.query.filter_by(
        community_id=community.id,
        deleted=False
    ).count()
    
    if page_num is None:
        # Return collection with first page reference
        collection = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": outbox_url,
            "type": "OrderedCollection",
            "totalItems": total_posts,
            "first": f"{outbox_url}?page=1",
            "last": f"{outbox_url}?page={(total_posts // 50) + 1}"
        }
        return make_activitypub_response(collection)
    
    # Return specific page
    items_per_page = 50
    offset = (page_num - 1) * items_per_page
    
    posts = Post.query.filter_by(
        community_id=community.id,
        deleted=False
    ).order_by(desc(Post.created_at)).offset(offset).limit(items_per_page).all()
    
    # Convert posts to Create activities
    items = []
    for post in posts:
        from app.activitypub.util import post_to_activity
        activity = post_to_activity(post, community)
        items.append(activity)
    
    # Build page
    page_data = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"{outbox_url}?page={page_num}",
        "type": "OrderedCollectionPage",
        "totalItems": total_posts,
        "partOf": outbox_url,
        "orderedItems": items
    }
    
    # Add navigation links
    if page_num > 1:
        page_data["prev"] = f"{outbox_url}?page={page_num - 1}"
    if offset + items_per_page < total_posts:
        page_data["next"] = f"{outbox_url}?page={page_num + 1}"
    
    return make_activitypub_response(page_data)


@bp.route('/c/<actor>/followers', methods=['GET'])
def community_followers(actor: ActorName) -> tuple[Dict[str, Any], int]:
    """
    Community followers collection endpoint.
    
    Lists all followers of a community. For privacy, we return
    only the count, not the actual follower list.
    
    Args:
        actor: Community name
        
    Returns:
        ActivityPub Collection with follower count
    """
    community = Community.query.filter_by(name=actor, banned=False).first()
    if not community:
        abort(404)
    
    # Get follower count
    follower_count = community_members(community.id)
    
    collection = Collection(
        id=f"https://{current_app.config['SERVER_NAME']}/c/{actor}/followers",
        type="Collection",
        totalItems=follower_count,
        items=None  # Privacy: don't expose actual followers
    )
    
    return make_activitypub_response(collection)


@bp.route('/c/<actor>/featured', methods=['GET'])
def community_featured(actor: ActorName) -> tuple[Dict[str, Any], int]:
    """
    Community featured/pinned posts collection.
    
    Lists posts that have been pinned by community moderators.
    
    Args:
        actor: Community name
        
    Returns:
        ActivityPub OrderedCollection of featured posts
    """
    community = Community.query.filter_by(name=actor, banned=False).first()
    if not community:
        abort(404)
    
    # Get featured/sticky posts
    featured_posts = Post.query.filter_by(
        community_id=community.id,
        deleted=False,
        sticky=True
    ).order_by(desc(Post.created_at)).all()
    
    # Convert to activities
    items = []
    for post in featured_posts:
        from app.activitypub.util import post_to_activity
        activity = post_to_activity(post, community)
        items.append(activity)
    
    collection = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://{current_app.config['SERVER_NAME']}/c/{actor}/featured",
        "type": "OrderedCollection",
        "totalItems": len(items),
        "orderedItems": items
    }
    
    return make_activitypub_response(collection)


@bp.route('/c/<actor>/moderators', methods=['GET'])
def community_moderators(actor: ActorName) -> tuple[Dict[str, Any], int]:
    """
    Community moderators collection endpoint.
    
    Lists moderators of a community. This is public information
    needed for moderation transparency.
    
    Args:
        actor: Community name
        
    Returns:
        ActivityPub Collection with moderator actor URLs
    """
    community = Community.query.filter_by(name=actor, banned=False).first()
    if not community:
        abort(404)
    
    # Get moderators
    moderators = CommunityMember.query.filter_by(
        community_id=community.id,
        is_moderator=True,
        is_banned=False
    ).all()
    
    # Build moderator list
    mod_list = []
    for mod in moderators:
        if mod.user and not mod.user.deleted and not mod.user.banned:
            mod_list.append(mod.user.public_url())
    
    collection = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://{current_app.config['SERVER_NAME']}/c/{actor}/moderators",
        "type": "OrderedCollection",
        "totalItems": len(mod_list),
        "orderedItems": mod_list
    }
    
    return make_activitypub_response(collection)


def _build_user_actor_object(user: User) -> ActorObject:
    """
    Build ActivityPub Person actor object for a user.
    
    Args:
        user: User model instance
        
    Returns:
        Complete Person actor object
    """
    server_name = current_app.config['SERVER_NAME']
    actor_url = f"https://{server_name}/u/{user.user_name}"
    
    actor = ActorObject(
        id=actor_url,
        type="Person",
        inbox=f"{actor_url}/inbox",
        outbox=f"{actor_url}/outbox",
        preferredUsername=user.user_name,
        name=user.title or user.user_name,
        summary=user.about_html if user.about_html else None,
        url=actor_url,
        manuallyApprovesFollowers=False,
        discoverable=user.searchable,
        publicKey={
            "id": f"{actor_url}#main-key",
            "owner": actor_url,
            "publicKeyPem": user.public_key or public_key()
        },
        endpoints={
            "sharedInbox": f"https://{server_name}/inbox"
        }
    )
    
    # Add optional fields
    if user.created_at:
        actor['published'] = ap_datetime(user.created_at)
    
    if user.avatar:
        actor['icon'] = {
            "type": "Image",
            "url": user.avatar_url()
        }
    
    if user.cover:
        actor['image'] = {
            "type": "Image", 
            "url": user.cover_url()
        }
    
    # Add collections
    actor['followers'] = f"{actor_url}/followers"
    actor['following'] = f"{actor_url}/following"
    actor['liked'] = f"{actor_url}/liked"
    
    # Add context
    actor['@context'] = [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ]
    
    return actor


@bp.route('/u/<actor>/followers', methods=['GET'])
def user_followers(actor: ActorName) -> tuple[Dict[str, Any], int]:
    """
    User followers collection endpoint.
    
    For privacy, returns only the count, not actual followers.
    
    Args:
        actor: Username
        
    Returns:
        ActivityPub Collection with follower count
    """
    user = User.query.filter_by(user_name=actor, deleted=False, banned=False).first()
    if not user:
        abort(404)
    
    # Get follower count
    from app.models import UserFollower
    follower_count = UserFollower.query.filter_by(
        followed_id=user.id
    ).count()
    
    collection = Collection(
        id=f"https://{current_app.config['SERVER_NAME']}/u/{actor}/followers",
        type="Collection",
        totalItems=follower_count,
        items=None  # Privacy: don't expose actual followers
    )
    
    return make_activitypub_response(collection)


@bp.route('/post/<int:post_id>/', methods=['GET', 'HEAD'])
@bp.route('/post/<int:post_id>', methods=['GET', 'HEAD', 'POST'])
def post_ap(post_id: int) -> Union[str, tuple[Dict[str, Any], int]]:
    """
    ActivityPub endpoint for individual posts.
    
    Args:
        post_id: Post ID
        
    Returns:
        ActivityPub Note/Article object or HTML redirect
    """
    post = Post.query.get_or_404(post_id)
    
    if post.deleted:
        abort(404)
    
    # If not an ActivityPub request, redirect to HTML view
    if not is_activitypub_request(request):
        return redirect(url_for('post.show_post', post_id=post_id))
    
    # Convert to ActivityPub object
    from app.activitypub.util import post_to_activity
    activity = post_to_activity(post, post.community)
    
    # Return just the object, not the Create activity
    object_data = activity.get('object', activity)
    
    return make_activitypub_response(object_data)


@bp.route('/post/<int:post_id>/replies', methods=['GET'])
def post_replies(post_id: int) -> tuple[Dict[str, Any], int]:
    """
    Get replies collection for a post.
    
    Args:
        post_id: Post ID
        
    Returns:
        ActivityPub Collection of replies
    """
    post = Post.query.get_or_404(post_id)
    
    if post.deleted:
        abort(404)
    
    # Get direct replies
    replies = PostReply.query.filter_by(
        post_id=post.id,
        parent_id=None,  # Top-level replies only
        deleted=False
    ).order_by(desc(PostReply.created_at)).all()
    
    # Convert to ActivityPub objects
    items = []
    for reply in replies:
        from app.activitypub.util import comment_model_to_json
        reply_obj = comment_model_to_json(reply)
        items.append(reply_obj)
    
    collection = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://{current_app.config['SERVER_NAME']}/post/{post_id}/replies",
        "type": "Collection",
        "totalItems": len(items),
        "items": items
    }
    
    return make_activitypub_response(collection)


@bp.route('/comment/<int:comment_id>', methods=['GET', 'HEAD'])
def comment_ap(comment_id: int) -> Union[str, tuple[Dict[str, Any], int]]:
    """
    ActivityPub endpoint for individual comments.
    
    Args:
        comment_id: Comment/PostReply ID
        
    Returns:
        ActivityPub Note object or HTML redirect
    """
    comment = PostReply.query.get_or_404(comment_id)
    
    if comment.deleted:
        abort(404)
    
    # If not an ActivityPub request, redirect to HTML view
    if not is_activitypub_request(request):
        return redirect(url_for('post.show_post', post_id=comment.post_id))
    
    # Convert to ActivityPub object
    from app.activitypub.util import comment_model_to_json
    comment_obj = comment_model_to_json(comment)
    
    return make_activitypub_response(comment_obj)


def _build_community_actor_object(community: Community) -> ActorObject:
    """
    Build ActivityPub Group actor object for a community.
    
    Includes Lemmy-specific extensions for full compatibility.
    
    Args:
        community: Community model instance
        
    Returns:
        Complete Group actor object with extensions
    """
    server_name = current_app.config['SERVER_NAME']
    actor_url = f"https://{server_name}/c/{community.name}"
    
    actor = ActorObject(
        id=actor_url,
        type="Group",
        inbox=f"{actor_url}/inbox",
        outbox=f"{actor_url}/outbox",
        preferredUsername=community.name,
        name=community.title or community.name,
        summary=community.description_html if community.description_html else None,
        url=actor_url,
        manuallyApprovesFollowers=community.restricted_to_mods,
        discoverable=True,
        publicKey={
            "id": f"{actor_url}#main-key",
            "owner": actor_url,
            "publicKeyPem": community.public_key or public_key()
        },
        endpoints={
            "sharedInbox": f"https://{server_name}/inbox"
        }
    )
    
    # Add community-specific fields
    actor['followers'] = f"{actor_url}/followers"
    actor['moderators'] = f"{actor_url}/moderators"
    actor['postingRestrictedToMods'] = community.restricted_to_mods
    actor['sensitive'] = community.nsfw or community.nsfl
    
    # Add optional fields
    if community.created_at:
        actor['published'] = ap_datetime(community.created_at)
    
    if community.icon:
        actor['icon'] = {
            "type": "Image",
            "url": community.icon_url()
        }
    
    if community.image:
        actor['image'] = {
            "type": "Image",
            "url": community.image_url()
        }
    
    # Add context with Lemmy extensions
    actor['@context'] = [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1",
        {
            "lemmy": "https://join-lemmy.org/ns#",
            "moderators": {"@type": "@id", "@id": "lemmy:moderators"},
            "postingRestrictedToMods": "lemmy:postingRestrictedToMods",
            "sensitive": "as:sensitive"
        }
    ]
    
    return actor