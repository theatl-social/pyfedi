"""ActivityPub object finding utilities with full type annotations"""
from __future__ import annotations
from typing import Optional, Union, overload
from datetime import datetime
from dateutil import parser
from flask import current_app

from app.models import Post, PostReply, User, Community, Instance
from app import db
from app.activitypub.util import find_actor_or_create
from app.activitypub.signature import signed_get_request
from app.utils import markdown_to_html

# Type aliases
ActivityPubObject = Union[Post, PostReply]
ActivityId = str
ActorUrl = str


@overload
def find_object(ap_id: ActivityId, resolve_remote: bool = True) -> Optional[ActivityPubObject]:
    ...

@overload  
def find_object(ap_id: ActivityId, resolve_remote: bool, object_type: type[Post]) -> Optional[Post]:
    ...

@overload
def find_object(ap_id: ActivityId, resolve_remote: bool, object_type: type[PostReply]) -> Optional[PostReply]:
    ...


def find_object(
    ap_id: ActivityId,
    resolve_remote: bool = True,
    object_type: Optional[type[ActivityPubObject]] = None
) -> Optional[ActivityPubObject]:
    """
    Attempts to find an ActivityPub object (Post or PostReply) locally.
    If not found and resolve_remote is True, attempts to fetch it remotely.
    
    Args:
        ap_id: The ActivityPub ID of the object to find
        resolve_remote: Whether to attempt remote resolution if not found locally
        object_type: Optionally restrict search to specific object type
        
    Returns:
        The found object or None if not found
    """
    # Try to find locally first
    if object_type is None or object_type is Post:
        obj = Post.get_by_ap_id(ap_id)
        if obj:
            return obj
    
    if object_type is None or object_type is PostReply:
        obj = PostReply.get_by_ap_id(ap_id)
        if obj:
            return obj
    
    # Try to fetch remotely if requested
    if resolve_remote:
        try:
            resolve_remote_object(ap_id)
        except Exception as e:
            current_app.logger.debug(f"Failed to resolve remote object {ap_id}: {e}")
    
        # Try again locally after remote fetch
        if object_type is None or object_type is Post:
            obj = Post.get_by_ap_id(ap_id)
            if obj:
                return obj
        
        if object_type is None or object_type is PostReply:
            obj = PostReply.get_by_ap_id(ap_id)
            if obj:
                return obj
    
    return None


def resolve_remote_object(ap_id: ActivityId) -> Optional[ActivityPubObject]:
    """
    Fetch and store a remote ActivityPub object.
    
    Args:
        ap_id: The ActivityPub ID of the object to fetch
        
    Returns:
        The created object or None if fetch failed
    """
    from urllib.parse import urlparse
    
    try:
        # Get local instance for signing
        local_instance = Instance.query.filter_by(id=1).first()
        if not local_instance or not local_instance.private_key:
            current_app.logger.error("No local instance configured for signing")
            return None
        
        # Make signed request
        response = signed_get_request(
            uri=ap_id,
            private_key=local_instance.private_key,
            key_id=f"https://{current_app.config['SERVER_NAME']}/actor#main-key"
        )
        
        if response.status_code != 200:
            current_app.logger.warning(f"Failed to fetch {ap_id}: {response.status_code}")
            return None
        
        data = response.json()
        object_type = data.get('type', '').lower()
        
        # Route to appropriate handler based on type
        if object_type in ['note', 'article', 'page', 'question']:
            return create_post_from_activity(data)
        elif object_type == 'comment':
            return create_reply_from_activity(data)
        else:
            current_app.logger.warning(f"Unknown object type: {object_type}")
            return None
            
    except Exception as e:
        current_app.logger.error(f"Error resolving remote object {ap_id}: {e}")
        return None


def create_post_from_activity(activity: dict) -> Optional[Post]:
    """Create a Post from an ActivityPub Note/Article/Page/Question"""
    try:
        # Find or create the author
        author = find_actor_or_create(activity['attributedTo'])
        if not author:
            return None
        
        # Find the community (from 'to' or 'cc' fields)
        community = None
        for recipient in activity.get('to', []) + activity.get('cc', []):
            if isinstance(recipient, str) and not recipient.endswith('#Public'):
                potential_community = find_actor_or_create(recipient)
                if isinstance(potential_community, Community):
                    community = potential_community
                    break
        
        if not community:
            current_app.logger.warning(f"No community found for post {activity['id']}")
            return None
        
        # Create the post
        post = Post(
            user_id=author.id,
            community_id=community.id,
            title=activity.get('name', activity.get('summary', 'Untitled')),
            body=activity.get('content', ''),
            body_html=activity.get('content', ''),
            ap_id=activity['id'],
            ap_create_id=activity.get('id'),
            ap_announce_id=None,
            score=1,
            up_votes=1,
            down_votes=0,
            ranking=0,
            type=1,  # POST_TYPE_ARTICLE
            comments_enabled=True,
            created_at=parse_ap_datetime(activity.get('published')),
            edited_at=parse_ap_datetime(activity.get('updated')),
            last_active=datetime.utcnow(),
            instance_id=author.instance_id,
            language='en',
            nsfw=activity.get('sensitive', False),
            nsfl=False,
            sticky=False,
            hot_rank=0
        )
        
        db.session.add(post)
        db.session.commit()
        
        return post
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating post from activity: {e}")
        return None


def create_reply_from_activity(activity: dict) -> Optional[PostReply]:
    """Create a PostReply from an ActivityPub Comment/Note in reply to something"""
    try:
        # Find or create the author
        author = find_actor_or_create(activity['attributedTo'])
        if not author:
            return None
        
        # Find the parent post or reply
        in_reply_to = activity.get('inReplyTo')
        if not in_reply_to:
            return None
        
        parent = find_object(in_reply_to, resolve_remote=True)
        if not parent:
            return None
        
        # Determine if replying to post or another reply
        if isinstance(parent, Post):
            post_id = parent.id
            parent_id = None
            depth = 0
        else:  # PostReply
            post_id = parent.post_id
            parent_id = parent.id
            depth = parent.depth + 1
        
        # Create the reply
        reply = PostReply(
            user_id=author.id,
            post_id=post_id,
            parent_id=parent_id,
            depth=depth,
            body=activity.get('content', ''),
            body_html=activity.get('content', ''),
            score=1,
            up_votes=1,
            down_votes=0,
            ranking=0,
            created_at=parse_ap_datetime(activity.get('published')),
            edited_at=parse_ap_datetime(activity.get('updated')),
            ap_id=activity['id'],
            ap_create_id=activity.get('id'),
            ap_announce_id=None,
            instance_id=author.instance_id,
            deleted=False,
            notified_users=''
        )
        
        db.session.add(reply)
        db.session.commit()
        
        return reply
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating reply from activity: {e}")
        return None


def parse_ap_datetime(datetime_str: Optional[str]) -> datetime:
    """Parse ActivityPub datetime string to Python datetime"""
    if not datetime_str:
        return datetime.utcnow()
    
    try:
        return parser.isoparse(datetime_str).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def find_actor(actor_url: ActorUrl) -> Optional[Union[User, Community]]:
    """Find an actor (User or Community) by URL without creating"""
    return find_actor_or_create(actor_url, create_if_not_found=False)