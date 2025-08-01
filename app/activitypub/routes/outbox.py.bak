"""
Outbox functionality for sending ActivityPub activities

This module handles the creation and sending of outbound ActivityPub
activities to other instances. It ensures proper formatting for
compatibility with different implementations.

Key functions:
    - send_activity: Queue an activity for delivery
    - send_to_followers: Distribute to all followers
    - send_create: Send a Create activity for new content
    - send_update: Send an Update activity for edits
    - send_delete: Send a Delete activity
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import asyncio

from flask import current_app
from sqlalchemy import select

from app import db
from app.models import User, Community, CommunityMember, Instance, Post, PostReply
from app.activitypub.signature import send_post_request
from app.federation.producer import get_producer
from app.utils import gibberish, ap_datetime, get_redis_connection

# Type aliases
type ActivityObject = Dict[str, Any]
type ActorUrl = str
type InboxUrl = str


async def send_activity(
    activity: ActivityObject,
    recipient_inbox: InboxUrl,
    sender_private_key: str,
    sender_key_id: str
) -> bool:
    """
    Queue an activity for delivery to a recipient.
    
    This is the main entry point for sending activities. It uses the
    Redis Streams producer to queue the activity for reliable delivery.
    
    Args:
        activity: The activity object to send
        recipient_inbox: Target inbox URL
        sender_private_key: Private key for signing
        sender_key_id: Key ID for signature
        
    Returns:
        True if successfully queued
        
    Example:
        >>> activity = {
        ...     "type": "Create",
        ...     "actor": "https://example.com/u/alice",
        ...     "object": {...}
        ... }
        >>> await send_activity(
        ...     activity,
        ...     "https://other.site/inbox",
        ...     private_key,
        ...     "https://example.com/u/alice#main-key"
        ... )
    """
    try:
        producer = get_producer()
        
        # Queue the activity
        message_id = await producer.queue_activity(
            activity=activity,
            destination=recipient_inbox,
            private_key=sender_private_key,
            key_id=sender_key_id
        )
        
        current_app.logger.info(
            f"Queued activity {activity.get('type')} to {recipient_inbox} "
            f"with message ID {message_id}"
        )
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Failed to queue activity: {e}")
        return False


async def send_to_followers(
    activity: ActivityObject,
    community: Community,
    exclude_actors: Optional[Set[ActorUrl]] = None
) -> int:
    """
    Send an activity to all followers of a community.
    
    This function handles the fan-out of activities to all followers,
    grouping by instance for efficiency.
    
    Args:
        activity: The activity to send
        community: The community whose followers to notify
        exclude_actors: Optional set of actor URLs to exclude
        
    Returns:
        Number of instances the activity was sent to
        
    Example:
        >>> post_activity = create_post_activity(post)
        >>> count = await send_to_followers(
        ...     post_activity,
        ...     post.community,
        ...     exclude_actors={post.author.ap_profile_id}
        ... )
        >>> print(f"Sent to {count} instances")
    """
    if exclude_actors is None:
        exclude_actors = set()
    
    # Get all followers grouped by instance
    followers_by_instance: Dict[int, List[User]] = {}
    
    members = CommunityMember.query.filter_by(
        community_id=community.id,
        is_banned=False
    ).all()
    
    for member in members:
        if member.user and member.user.instance_id:
            # Skip excluded actors
            if member.user.ap_profile_id in exclude_actors:
                continue
                
            # Skip local users (they already have the content)
            if member.user.instance_id == 1:
                continue
            
            # Group by instance
            if member.user.instance_id not in followers_by_instance:
                followers_by_instance[member.user.instance_id] = []
            followers_by_instance[member.user.instance_id].append(member.user)
    
    # Send to each instance's shared inbox
    sent_count = 0
    producer = get_producer()
    
    for instance_id, users in followers_by_instance.items():
        instance = Instance.query.get(instance_id)
        if not instance or instance.dormant or instance.gone_forever:
            continue
        
        # Use shared inbox if available
        inbox_url = instance.shared_inbox or f"https://{instance.domain}/inbox"
        
        try:
            # Batch queue for this instance
            await producer.queue_activity(
                activity=activity,
                destination=inbox_url,
                private_key=community.private_key,
                key_id=f"{community.ap_profile_id}#main-key"
            )
            sent_count += 1
            
        except Exception as e:
            current_app.logger.error(
                f"Failed to queue activity to {instance.domain}: {e}"
            )
    
    return sent_count


def create_post_activity(post: Post) -> ActivityObject:
    """
    Create a Create activity for a new post.
    
    Formats the post as an ActivityPub Create activity with proper
    addressing and object structure.
    
    Args:
        post: The post to create an activity for
        
    Returns:
        Create activity object
    """
    from app.activitypub.util import post_to_activity
    
    # Get the base activity from util
    activity = post_to_activity(post, post.community)
    
    # Ensure proper structure
    if '@context' not in activity:
        activity['@context'] = [
            "https://www.w3.org/ns/activitystreams",
            "https://w3id.org/security/v1"
        ]
    
    return activity


def create_update_activity(
    updated_object: Union[Post, PostReply, User, Community]
) -> ActivityObject:
    """
    Create an Update activity for edited content.
    
    Args:
        updated_object: The object that was updated
        
    Returns:
        Update activity object
    """
    activity_id = f"https://{current_app.config['SERVER_NAME']}/activities/update/{gibberish(15)}"
    
    # Determine actor and object URLs
    if isinstance(updated_object, (Post, PostReply)):
        actor = updated_object.author.ap_profile_id
        object_data = _serialize_content(updated_object)
    elif isinstance(updated_object, User):
        actor = updated_object.ap_profile_id
        object_data = _serialize_actor(updated_object)
    elif isinstance(updated_object, Community):
        actor = updated_object.ap_profile_id
        object_data = _serialize_actor(updated_object)
    else:
        raise ValueError(f"Unknown object type: {type(updated_object)}")
    
    activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": activity_id,
        "type": "Update",
        "actor": actor,
        "object": object_data,
        "published": ap_datetime(datetime.now(timezone.utc))
    }
    
    # Add addressing
    if isinstance(updated_object, (Post, PostReply)):
        activity["to"] = ["https://www.w3.org/ns/activitystreams#Public"]
        activity["cc"] = [updated_object.community.ap_profile_id]
    
    return activity


def create_delete_activity(
    deleted_object: Union[Post, PostReply, User, Community],
    is_soft_delete: bool = True
) -> ActivityObject:
    """
    Create a Delete activity.
    
    Args:
        deleted_object: The object being deleted
        is_soft_delete: If True, object can be restored
        
    Returns:
        Delete activity object
    """
    activity_id = f"https://{current_app.config['SERVER_NAME']}/activities/delete/{gibberish(15)}"
    
    # Determine actor
    if isinstance(deleted_object, (Post, PostReply)):
        actor = deleted_object.author.ap_profile_id
        object_id = deleted_object.ap_id
    else:
        actor = deleted_object.ap_profile_id
        object_id = deleted_object.ap_profile_id
    
    activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": activity_id,
        "type": "Delete",
        "actor": actor,
        "object": object_id,
        "published": ap_datetime(datetime.now(timezone.utc))
    }
    
    # Add addressing for content deletions
    if isinstance(deleted_object, (Post, PostReply)):
        activity["to"] = ["https://www.w3.org/ns/activitystreams#Public"]
        activity["cc"] = [deleted_object.community.ap_profile_id]
    
    return activity


def create_like_activity(
    user: User,
    liked_object: Union[Post, PostReply]
) -> ActivityObject:
    """
    Create a Like activity (upvote).
    
    Args:
        user: The user doing the liking
        liked_object: The post or comment being liked
        
    Returns:
        Like activity object
    """
    activity_id = f"https://{current_app.config['SERVER_NAME']}/activities/like/{gibberish(15)}"
    
    activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": activity_id,
        "type": "Like",
        "actor": user.ap_profile_id,
        "object": liked_object.ap_id,
        "published": ap_datetime(datetime.now(timezone.utc)),
        "to": [liked_object.author.ap_profile_id],
        "cc": ["https://www.w3.org/ns/activitystreams#Public"]
    }
    
    return activity


def create_undo_activity(
    actor: Union[User, Community],
    undone_activity: ActivityObject
) -> ActivityObject:
    """
    Create an Undo activity.
    
    Args:
        actor: The actor undoing the activity
        undone_activity: The activity being undone
        
    Returns:
        Undo activity object
    """
    activity_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"
    
    activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": activity_id,
        "type": "Undo",
        "actor": actor.ap_profile_id,
        "object": undone_activity,
        "published": ap_datetime(datetime.now(timezone.utc))
    }
    
    # Copy addressing from undone activity
    if "to" in undone_activity:
        activity["to"] = undone_activity["to"]
    if "cc" in undone_activity:
        activity["cc"] = undone_activity["cc"]
    
    return activity


def create_announce_activity(
    community: Community,
    announced_object: Union[Post, ActivityObject]
) -> ActivityObject:
    """
    Create an Announce activity (boost/share).
    
    Communities use Announce to share posts with their followers.
    
    Args:
        community: The community doing the announcing
        announced_object: The post or activity being announced
        
    Returns:
        Announce activity object
    """
    activity_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
    
    # Get object ID
    if isinstance(announced_object, Post):
        object_id = announced_object.ap_id
    elif isinstance(announced_object, dict):
        object_id = announced_object.get('id', announced_object)
    else:
        object_id = str(announced_object)
    
    activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": activity_id,
        "type": "Announce",
        "actor": community.ap_profile_id,
        "object": object_id,
        "published": ap_datetime(datetime., timezone()),
        "to": ["https://www.w3.org/ns/activitystreams#Public"],
        "cc": [f"{community.ap_profile_id}/followers"]
    }
    
    return activity


def _serialize_content(
    content: Union[Post, PostReply]
) -> Dict[str, Any]:
    """
    Serialize a post or comment to ActivityPub object.
    
    Args:
        content: Post or PostReply to serialize
        
    Returns:
        Serialized object
    """
    if isinstance(content, Post):
        object_type = "Article" if content.type == 1 else "Note"
        in_reply_to = None
    else:
        object_type = "Note"
        in_reply_to = content.parent.ap_id if content.parent else content.post.ap_id
    
    obj = {
        "id": content.ap_id,
        "type": object_type,
        "attributedTo": content.author.ap_profile_id,
        "content": content.body_html or "",
        "source": {
            "content": content.body or "",
            "mediaType": "text/markdown"
        },
        "published": ap_datetime(content.created_at),
        "to": ["https://www.w3.org/ns/activitystreams#Public"],
        "cc": [content.community.ap_profile_id]
    }
    
    # Add optional fields
    if isinstance(content, Post) and content.title:
        obj["name"] = content.title
    
    if content.edited_at:
        obj["updated"] = ap_datetime(content.edited_at)
    
    if in_reply_to:
        obj["inReplyTo"] = in_reply_to
    
    if hasattr(content, 'sensitive') and content.sensitive:
        obj["sensitive"] = True
    
    return obj


def _serialize_actor(
    actor: Union[User, Community]
) -> Dict[str, Any]:
    """
    Serialize a user or community to ActivityPub actor object.
    
    Args:
        actor: User or Community to serialize
        
    Returns:
        Serialized actor object
    """
    from app.activitypub.routes.actors import (
        _build_user_actor_object,
        _build_community_actor_object
    )
    
    if isinstance(actor, User):
        return _build_user_actor_object(actor)
    else:
        return _build_community_actor_object(actor)