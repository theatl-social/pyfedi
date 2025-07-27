"""Follow/Unfollow tasks migrated to Redis Streams"""
from typing import Optional, Dict, Any
from flask import current_app, flash
from markupsafe import Markup
from flask_babel import _

from app import cache, db
from app.constants import *
from app.federation.tasks import task, Priority
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import Community, CommunityBan, CommunityJoinRequest, User, CommunityMember
from app.utils import community_membership, gibberish, joined_communities, instance_banned, get_task_session


@task(name='join_community', priority=Priority.URGENT)
def join_community(send_async: bool, user_id: int, community_id: int, src: str) -> Optional[Dict[str, Any]]:
    """
    Process a user joining a community
    
    Args:
        send_async: Whether processing asynchronously
        user_id: ID of the user joining
        community_id: ID of the community to join
        src: Source of the request (SRC_WEB, SRC_API, etc.)
        
    Returns:
        Pre-load message for API responses (when async) or None
    """
    session = get_task_session()
    try:
        user = session.query(User).filter_by(id=user_id).one()
        community = session.query(Community).filter_by(id=community_id).one()

        pre_load_message = {}
        
        # Check if user is banned
        banned = session.query(CommunityBan).filter_by(
            user_id=user_id, 
            community_id=community_id
        ).first()
        
        if banned:
            if not send_async:
                if src == SRC_WEB:
                    flash(_('You cannot join this community'))
                    return None
                else:
                    pre_load_message = {'message': _('You cannot join this community'), 'status': 'error'}
            return pre_load_message
            
        # Check instance blocks
        if not community.is_local():
            if user.has_blocked_instance(community.instance_id) or instance_banned(community.instance.domain):
                if not send_async:
                    if src == SRC_WEB:
                        flash(_('You cannot join this community from an instance you have blocked'))
                        return None
                    else:
                        pre_load_message = {
                            'message': _('You cannot join this community from an instance you have blocked'), 
                            'status': 'error'
                        }
                return pre_load_message

        # Clear caches
        cache.delete_memoized(community_membership, user, community)
        cache.delete_memoized(joined_communities, user.id)

        # Check existing membership
        existing_membership = session.query(CommunityMember).filter_by(
            user_id=user_id,
            community_id=community_id
        ).first()
        
        if existing_membership:
            if not send_async:
                if src == SRC_WEB:
                    flash(_('You are already a member of this community'))
                else:
                    pre_load_message = {
                        'message': _('You are already a member of this community'), 
                        'status': 'error'
                    }
            return pre_load_message

        # Create join request or membership
        if send_async:
            # For async, just create join request
            join_request = CommunityJoinRequest(
                user_id=user_id,
                community_id=community_id
            )
            session.add(join_request)
            session.commit()
        else:
            # For sync, create actual membership
            member = CommunityMember(
                user_id=user_id,
                community_id=community_id,
                is_moderator=False,
                is_owner=False
            )
            session.add(member)
            
            # Update community stats
            community.subscriptions_count += 1
            session.commit()
            
            if src == SRC_WEB:
                flash(Markup(_('You have joined <a href="/c/%(name)s">%(name)s</a>',
                             name=community.name)))

        # Send Follow activity if needed
        if community.ap_id:  # Remote community
            follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{gibberish(15)}"
            
            follow_activity = {
                '@context': default_context(),
                'id': follow_id,
                'type': 'Follow',
                'actor': user.public_url(),
                'object': community.public_url(),
                'to': [community.public_url()]
            }
            
            send_post_request(
                community.ap_inbox_url,
                follow_activity,
                user.private_key,
                user.public_url() + '#main-key'
            )
            
            pre_load_message = {
                'message': _('Follow request sent. Awaiting approval.'),
                'status': 'pending'
            }

        return pre_load_message
        
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@task(name='leave_community', priority=Priority.URGENT)
def leave_community(send_async: bool, user_id: int, community_id: int, src: str) -> Optional[Dict[str, Any]]:
    """
    Process a user leaving a community
    
    Args:
        send_async: Whether processing asynchronously
        user_id: ID of the user leaving
        community_id: ID of the community to leave
        src: Source of the request (SRC_WEB, SRC_API, etc.)
        
    Returns:
        Pre-load message for API responses (when async) or None
    """
    session = get_task_session()
    try:
        user = session.query(User).filter_by(id=user_id).one()
        community = session.query(Community).filter_by(id=community_id).one()

        # Clear caches
        cache.delete_memoized(community_membership, user, community)
        cache.delete_memoized(joined_communities, user.id)

        # Remove membership
        membership = session.query(CommunityMember).filter_by(
            user_id=user_id,
            community_id=community_id
        ).first()
        
        if membership:
            session.delete(membership)
            community.subscriptions_count -= 1
            session.commit()
            
            if not send_async and src == SRC_WEB:
                flash(Markup(_('You have left <a href="/c/%(name)s">%(name)s</a>',
                             name=community.name)))
        
        # Send Undo Follow activity if needed
        if community.ap_id:  # Remote community
            follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{gibberish(15)}"
            undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"
            
            undo_activity = {
                '@context': default_context(),
                'id': undo_id,
                'type': 'Undo',
                'actor': user.public_url(),
                'object': {
                    'id': follow_id,
                    'type': 'Follow',
                    'actor': user.public_url(),
                    'object': community.public_url()
                },
                'to': [community.public_url()]
            }
            
            send_post_request(
                community.ap_inbox_url,
                undo_activity,
                user.private_key,
                user.public_url() + '#main-key'
            )

        return None
        
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Export tasks
__all__ = ['join_community', 'leave_community']