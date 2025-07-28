"""Typed ActivityPub utilities using Python 3.13 features"""
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple, Union, Literal, TypedDict, Protocol
from datetime import datetime
from pathlib import Path

from app.models_typed import TypedUser, TypedCommunity, TypedPost, TypedPostReply, TypedInstance
from app.federation.types import ActivityObject, ActorUrl, ActivityId, HttpUrl

# Type aliases
type CommunityId = int
type UserId = int
type PostId = int
type FileId = int
type InstanceId = int

# ActivityPub object types
class ActorObject(TypedDict, total=False):
    """ActivityPub Actor object"""
    id: str
    type: Literal["Person", "Group", "Service", "Application", "Organization"]
    inbox: str
    outbox: str
    followers: str
    following: str
    liked: str
    publicKey: Dict[str, str]
    preferredUsername: str
    name: Optional[str]
    summary: Optional[str]
    icon: Optional[Dict[str, str]]
    image: Optional[Dict[str, str]]
    url: Optional[str]
    manuallyApprovesFollowers: bool
    discoverable: bool
    published: Optional[str]
    updated: Optional[str]
    "@context": Union[str, List[str], Dict[str, Any]]

class NoteObject(TypedDict, total=False):
    """ActivityPub Note/Article object"""
    id: str
    type: Literal["Note", "Article", "Page", "Question"]
    attributedTo: str
    to: List[str]
    cc: List[str]
    inReplyTo: Optional[str]
    content: str
    contentMap: Optional[Dict[str, str]]
    summary: Optional[str]
    sensitive: bool
    attachment: Optional[List[Dict[str, Any]]]
    tag: Optional[List[Dict[str, Any]]]
    published: str
    updated: Optional[str]
    url: Optional[str]
    "@context": Union[str, List[str], Dict[str, Any]]

class CreateActivity(TypedDict):
    """Create activity"""
    id: str
    type: Literal["Create"]
    actor: str
    object: Union[NoteObject, str]
    to: List[str]
    cc: List[str]
    published: str
    "@context": Union[str, List[str], Dict[str, Any]]

class AnnounceActivity(TypedDict):
    """Announce (boost/share) activity"""
    id: str
    type: Literal["Announce"]
    actor: str
    object: Union[str, ActivityObject]
    to: List[str]
    cc: List[str]
    published: str
    "@context": Union[str, List[str], Dict[str, Any]]

# Function signatures with proper typing
def public_key() -> str:
    """Get or generate public key for ActivityPub signing"""
    public_key_path = Path('./public.pem')
    private_key_path = Path('./private.pem')
    
    if not public_key_path.exists():
        import subprocess
        subprocess.run(['openssl', 'genrsa', '-out', str(private_key_path), '2048'], check=True)
        subprocess.run(['openssl', 'rsa', '-in', str(private_key_path), '-outform', 'PEM', '-pubout', '-out', str(public_key_path)], check=True)
    
    public_key_content = public_key_path.read_text()
    # JSON-LD doesn't handle linebreaks well, needs \n character
    return public_key_content.replace('\n', '\\n')

def community_members(community_id: CommunityId) -> int:
    """Get count of active members in a community"""
    from sqlalchemy import text
    from app import db
    
    sql = '''
        SELECT COUNT(id) as c 
        FROM "user" as u 
        INNER JOIN community_member cm ON u.id = cm.user_id 
        WHERE u.banned IS FALSE 
          AND u.deleted IS FALSE 
          AND cm.is_banned IS FALSE 
          AND cm.community_id = :community_id
    '''
    return db.session.execute(text(sql), {'community_id': community_id}).scalar() or 0

def users_total() -> int:
    """Get total count of local verified users"""
    from sqlalchemy import text
    from app import db
    
    return db.session.execute(text(
        'SELECT COUNT(id) as c FROM "user" WHERE ap_id IS NULL AND verified IS TRUE AND banned IS FALSE AND deleted IS FALSE'
    )).scalar() or 0

def active_half_year() -> int:
    """Get count of users active in last 6 months"""
    from sqlalchemy import text
    from app import db
    
    return db.session.execute(text(
        "SELECT COUNT(id) as c FROM \"user\" WHERE last_seen >= CURRENT_DATE - INTERVAL '6 months' AND ap_id IS NULL AND verified IS TRUE AND banned IS FALSE AND deleted IS FALSE"
    )).scalar() or 0

def active_month() -> int:
    """Get count of users active in last month"""
    from sqlalchemy import text
    from app import db
    
    return db.session.execute(text(
        "SELECT COUNT(id) as c FROM \"user\" WHERE last_seen >= CURRENT_DATE - INTERVAL '1 month' AND ap_id IS NULL AND verified IS TRUE AND banned IS FALSE AND deleted IS FALSE"
    )).scalar() or 0

def active_week() -> int:
    """Get count of users active in last week"""
    from sqlalchemy import text
    from app import db
    
    return db.session.execute(text(
        "SELECT COUNT(id) as c FROM \"user\" WHERE last_seen >= CURRENT_DATE - INTERVAL '1 week' AND ap_id IS NULL AND verified IS TRUE AND banned IS FALSE AND deleted IS FALSE"
    )).scalar() or 0

def active_day() -> int:
    """Get count of users active in last day"""
    from sqlalchemy import text
    from app import db
    
    return db.session.execute(text(
        "SELECT COUNT(id) as c FROM \"user\" WHERE last_seen >= CURRENT_DATE - INTERVAL '1 day' AND ap_id IS NULL AND verified IS TRUE AND banned IS FALSE AND deleted IS FALSE"
    )).scalar() or 0

def local_posts() -> int:
    """Get count of local posts"""
    from sqlalchemy import text
    from app import db
    
    return db.session.execute(
        text('SELECT COUNT(id) as c FROM "post" WHERE instance_id = 1 AND deleted IS FALSE')
    ).scalar() or 0

def local_comments() -> int:
    """Get count of local comments"""
    from sqlalchemy import text
    from app import db
    
    return db.session.execute(
        text('SELECT COUNT(id) as c FROM "post_reply" WHERE instance_id = 1 AND deleted IS FALSE')
    ).scalar() or 0

def local_communities() -> int:
    """Get count of local communities"""
    from sqlalchemy import text
    from app import db
    
    return db.session.execute(
        text('SELECT COUNT(id) as c FROM "community" WHERE instance_id = 1')
    ).scalar() or 0

def post_to_activity(post: TypedPost, community: TypedCommunity) -> CreateActivity:
    """Convert a Post to an ActivityPub Create activity"""
    from flask import current_app
    from app.utils import gibberish, ap_datetime
    
    # Generate create ID if not present
    create_id = post.ap_create_id if post.ap_create_id else f"https://{current_app.config['SERVER_NAME']}/activities/create/{gibberish(15)}"
    
    # Build the Note object
    note: NoteObject = {
        "id": post.public_url(),
        "type": "Article" if post.type == POST_TYPE_ARTICLE else "Note",
        "attributedTo": post.author.public_url(),
        "to": ["https://www.w3.org/ns/activitystreams#Public"],
        "cc": [community.public_url(), post.author.ap_followers_url or ""],
        "content": post.body_html or "",
        "contentMap": {
            post.language or "en": post.body_html or ""
        } if post.language else None,
        "sensitive": post.nsfw or post.nsfl,
        "published": ap_datetime(post.created_at),
        "updated": ap_datetime(post.edited_at) if post.edited_at else None,
        "@context": "https://www.w3.org/ns/activitystreams"
    }
    
    # Add title for articles
    if post.title:
        note["name"] = post.title
    
    # Add summary if present
    if hasattr(post, 'summary') and post.summary:
        note["summary"] = post.summary
    
    # Add attachments
    if post.image_path or post.url:
        note["attachment"] = []
        if post.image_path:
            note["attachment"].append({
                "type": "Image",
                "url": f"https://{current_app.config['SERVER_NAME']}/media/{post.image_path}"
            })
        if post.url and is_video_url(post.url):
            note["attachment"].append({
                "type": "Video",
                "url": post.url
            })
    
    # Add tags
    if hasattr(post, 'tags') and post.tags:
        note["tag"] = [
            {
                "type": "Hashtag",
                "name": f"#{tag.name}",
                "href": f"https://{current_app.config['SERVER_NAME']}/tag/{tag.name}"
            }
            for tag in post.tags
        ]
    
    # Build the Create activity
    activity: CreateActivity = {
        "id": create_id,
        "type": "Create",
        "actor": post.author.public_url(),
        "object": note,
        "to": ["https://www.w3.org/ns/activitystreams#Public"],
        "cc": [community.public_url()],
        "published": ap_datetime(post.created_at),
        "@context": "https://www.w3.org/ns/activitystreams"
    }
    
    return activity

def extract_domain_and_actor(url: str) -> Tuple[str, str]:
    """Extract domain and actor name from an ActivityPub URL"""
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Handle different URL patterns
    path_parts = parsed.path.strip('/').split('/')
    
    # Common patterns:
    # https://example.com/users/username
    # https://example.com/u/username
    # https://example.com/@username
    # https://example.com/c/communityname
    
    if len(path_parts) >= 2:
        if path_parts[0] in ['users', 'u', 'c']:
            return domain, path_parts[1]
        elif path_parts[0].startswith('@'):
            return domain, path_parts[0][1:]
    elif len(path_parts) == 1 and path_parts[0].startswith('@'):
        return domain, path_parts[0][1:]
    
    # Fallback - use the last part of the path
    return domain, path_parts[-1] if path_parts else ""

def find_actor_or_create(
    actor_url: str,
    signed_get: bool = True,
    create_if_not_found: bool = True
) -> Optional[Union[TypedUser, TypedCommunity]]:
    """Find an actor (User or Community) by URL, optionally creating if not found"""
    from app.models import User, Community
    from app import db
    
    # First check if we already have this actor
    user = User.query.filter_by(ap_id=actor_url).first()
    if user:
        return user
    
    community = Community.query.filter_by(ap_id=actor_url).first()
    if community:
        return community
    
    if not create_if_not_found:
        return None
    
    # Fetch the actor from the remote instance
    try:
        if signed_get:
            from app.activitypub.signature import signed_get_request
            response = signed_get_request(actor_url)
        else:
            import httpx
            response = httpx.get(
                actor_url,
                headers={'Accept': 'application/activity+json'},
                timeout=30.0,
                follow_redirects=True
            )
        
        if response.status_code != 200:
            return None
        
        actor_data = response.json()
        
        # Determine actor type and create
        actor_type = actor_data.get('type', '').lower()
        
        if actor_type == 'person':
            return create_user_from_actor(actor_data)
        elif actor_type == 'group':
            return create_community_from_actor(actor_data)
        
    except Exception as e:
        current_app.logger.error(f"Error fetching actor {actor_url}: {e}")
        return None

def create_user_from_actor(actor_data: Dict[str, Any]) -> Optional[TypedUser]:
    """Create a User from ActivityPub actor data"""
    from app.models import User, Instance
    from app import db
    
    try:
        domain, username = extract_domain_and_actor(actor_data['id'])
        
        # Get or create instance
        instance = Instance.query.filter_by(domain=domain).first()
        if not instance:
            instance = Instance(
                domain=domain,
                inbox=actor_data.get('endpoints', {}).get('sharedInbox'),
                software='unknown'
            )
            db.session.add(instance)
            db.session.flush()
        
        user = User(
            user_name=username,
            ap_id=actor_data['id'],
            ap_domain=domain,
            ap_public_url=actor_data.get('url', actor_data['id']),
            ap_inbox_url=actor_data['inbox'],
            ap_outbox_url=actor_data.get('outbox'),
            ap_followers_url=actor_data.get('followers'),
            ap_preferred_username=actor_data.get('preferredUsername', username),
            ap_discoverable=actor_data.get('discoverable', False),
            ap_manually_approves_followers=actor_data.get('manuallyApprovesFollowers', False),
            title=actor_data.get('name'),
            about=actor_data.get('summary'),
            public_key=actor_data.get('publicKey', {}).get('publicKeyPem'),
            instance_id=instance.id,
            ap_fetched_at=datetime.utcnow()
        )
        
        db.session.add(user)
        db.session.commit()
        
        return user
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user from actor: {e}")
        return None

def create_community_from_actor(actor_data: Dict[str, Any]) -> Optional[TypedCommunity]:
    """Create a Community from ActivityPub actor data"""
    from app.models import Community, Instance
    from app import db
    
    try:
        domain, name = extract_domain_and_actor(actor_data['id'])
        
        # Get or create instance
        instance = Instance.query.filter_by(domain=domain).first()
        if not instance:
            instance = Instance(
                domain=domain,
                inbox=actor_data.get('endpoints', {}).get('sharedInbox'),
                software='unknown'
            )
            db.session.add(instance)
            db.session.flush()
        
        community = Community(
            name=name,
            title=actor_data.get('name', name),
            description=actor_data.get('summary'),
            ap_id=actor_data['id'],
            ap_domain=domain,
            ap_public_url=actor_data.get('url', actor_data['id']),
            ap_inbox_url=actor_data['inbox'],
            ap_outbox_url=actor_data.get('outbox'),
            ap_followers_url=actor_data.get('followers'),
            ap_moderators_url=actor_data.get('attributedTo'),
            ap_featured_url=actor_data.get('featured'),
            public_key=actor_data.get('publicKey', {}).get('publicKeyPem'),
            instance_id=instance.id,
            ap_fetched_at=datetime.utcnow()
        )
        
        db.session.add(community)
        db.session.commit()
        
        return community
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating community from actor: {e}")
        return None