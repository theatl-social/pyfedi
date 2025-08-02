"""
Permission validation for ActivityPub actions
Prevents privilege escalation and unauthorized actions
"""
from typing import Dict, Any, Optional, List
from app.models import User, Community, Post, CommunityMember, Site, db
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Permission(Enum):
    """Permission types"""
    CREATE_POST = "create_post"
    UPDATE_POST = "update_post"
    DELETE_POST = "delete_post"
    CREATE_COMMENT = "create_comment"
    UPDATE_COMMENT = "update_comment"
    DELETE_COMMENT = "delete_comment"
    MODERATE_CONTENT = "moderate_content"
    MANAGE_COMMUNITY = "manage_community"
    ADD_MODERATOR = "add_moderator"
    REMOVE_MODERATOR = "remove_moderator"
    BAN_USER = "ban_user"
    UNBAN_USER = "unban_user"
    PIN_POST = "pin_post"
    LOCK_POST = "lock_post"
    REMOVE_CONTENT = "remove_content"
    UPDATE_COMMUNITY = "update_community"
    DELETE_COMMUNITY = "delete_community"


class PermissionValidator:
    """Validate permissions for ActivityPub actions"""
    
    def __init__(self):
        self.role_permissions = {
            'admin': list(Permission),  # All permissions
            'moderator': [
                Permission.MODERATE_CONTENT,
                Permission.REMOVE_CONTENT,
                Permission.PIN_POST,
                Permission.LOCK_POST,
                Permission.BAN_USER,
                Permission.UNBAN_USER
            ],
            'member': [
                Permission.CREATE_POST,
                Permission.CREATE_COMMENT,
                Permission.UPDATE_POST,  # Own posts only
                Permission.UPDATE_COMMENT,  # Own comments only
                Permission.DELETE_POST,  # Own posts only
                Permission.DELETE_COMMENT  # Own comments only
            ],
            'banned': []  # No permissions
        }
    
    def validate_action(self, actor: User, action: str, target: Any, 
                       community: Optional[Community] = None) -> tuple[bool, Optional[str]]:
        """
        Validate if actor can perform action on target
        
        Returns:
            (allowed, reason_if_denied)
        """
        # Map action to permission
        permission = self._action_to_permission(action)
        if not permission:
            return False, f"Unknown action: {action}"
        
        # Check if actor is banned globally
        if self._is_globally_banned(actor):
            return False, "Actor is globally banned"
        
        # Check community-specific permissions
        if community:
            if not self._check_community_permission(actor, permission, community):
                return False, f"No permission for {permission.value} in community"
        
        # Check target ownership for update/delete
        if permission in [Permission.UPDATE_POST, Permission.DELETE_POST,
                          Permission.UPDATE_COMMENT, Permission.DELETE_COMMENT]:
            if not self._owns_target(actor, target):
                # Check if user is moderator
                if not community or not self._is_moderator(actor, community):
                    return False, "Can only modify own content"
        
        # Validate specific permissions
        if permission == Permission.ADD_MODERATOR:
            return self._validate_add_moderator(actor, target, community)
        elif permission == Permission.REMOVE_MODERATOR:
            return self._validate_remove_moderator(actor, target, community)
        elif permission == Permission.BAN_USER:
            return self._validate_ban_user(actor, target, community)
        elif permission == Permission.UPDATE_COMMUNITY:
            return self._validate_update_community(actor, community)
        elif permission == Permission.DELETE_COMMUNITY:
            return self._validate_delete_community(actor, community)
        
        return True, None
    
    def validate_group_action(self, group_activity: Dict[str, Any], actor: User) -> tuple[bool, Optional[str]]:
        """
        Validate group/community actions
        
        Returns:
            (allowed, reason_if_denied)
        """
        activity_type = group_activity.get('type')
        
        # Only certain types can be group activities
        allowed_group_types = ['Create', 'Update', 'Delete', 'Add', 'Remove', 'Block', 'Announce']
        if activity_type not in allowed_group_types:
            return False, f"Invalid group activity type: {activity_type}"
        
        # Extract attributed actor (who performed the action)
        attributed_to = group_activity.get('attributedTo')
        if not attributed_to:
            return False, "Group activity missing attributedTo"
        
        # Verify the attributed actor matches the signing actor
        if isinstance(attributed_to, str):
            if attributed_to != actor.ap_profile_id:
                return False, "Actor mismatch in group activity"
        elif isinstance(attributed_to, dict):
            if attributed_to.get('id') != actor.ap_profile_id:
                return False, "Actor mismatch in group activity"
        
        # Check if actor has permission to act on behalf of group
        group_actor = group_activity.get('actor')
        if isinstance(group_actor, str):
            community = Community.query.filter_by(ap_profile_id=group_actor).first()
            if community and not self._can_act_for_community(actor, community):
                return False, "No permission to act for this community"
        
        return True, None
    
    def _action_to_permission(self, action: str) -> Optional[Permission]:
        """Map ActivityPub action to permission"""
        action_map = {
            'Create': Permission.CREATE_POST,
            'Update': Permission.UPDATE_POST,
            'Delete': Permission.DELETE_POST,
            'Add': Permission.ADD_MODERATOR,
            'Remove': Permission.REMOVE_MODERATOR,
            'Block': Permission.BAN_USER,
            'Undo/Block': Permission.UNBAN_USER,
            'Pin': Permission.PIN_POST,
            'Lock': Permission.LOCK_POST
        }
        return action_map.get(action)
    
    def _is_globally_banned(self, actor: User) -> bool:
        """Check if actor is banned at instance level"""
        return actor.is_banned or (actor.instance and actor.instance.blocked)
    
    def _check_community_permission(self, actor: User, permission: Permission, 
                                  community: Community) -> bool:
        """Check if actor has permission in community"""
        # Get membership
        membership = CommunityMember.query.filter_by(
            user_id=actor.id,
            community_id=community.id
        ).first()
        
        if not membership:
            # Non-members can only create posts if community allows it
            return permission == Permission.CREATE_POST and community.allow_non_members_to_post
        
        # Check if banned from community
        if membership.is_banned:
            return False
        
        # Get role permissions
        role = 'admin' if membership.is_admin else 'moderator' if membership.is_moderator else 'member'
        allowed_permissions = self.role_permissions.get(role, [])
        
        return permission in allowed_permissions
    
    def _owns_target(self, actor: User, target: Any) -> bool:
        """Check if actor owns the target object"""
        if hasattr(target, 'author_id'):
            return target.author_id == actor.id
        elif hasattr(target, 'user_id'):
            return target.user_id == actor.id
        return False
    
    def _is_moderator(self, actor: User, community: Community) -> bool:
        """Check if actor is moderator of community"""
        membership = CommunityMember.query.filter_by(
            user_id=actor.id,
            community_id=community.id
        ).first()
        return membership and (membership.is_moderator or membership.is_admin)
    
    def _can_act_for_community(self, actor: User, community: Community) -> bool:
        """Check if actor can perform actions on behalf of community"""
        membership = CommunityMember.query.filter_by(
            user_id=actor.id,
            community_id=community.id
        ).first()
        # Only admins and moderators can act for community
        return membership and (membership.is_admin or membership.is_moderator)
    
    def _validate_add_moderator(self, actor: User, target_user: User, 
                               community: Community) -> tuple[bool, Optional[str]]:
        """Validate adding a moderator"""
        # Must be admin
        membership = CommunityMember.query.filter_by(
            user_id=actor.id,
            community_id=community.id
        ).first()
        
        if not membership or not membership.is_admin:
            return False, "Only admins can add moderators"
        
        # Target must be member
        target_membership = CommunityMember.query.filter_by(
            user_id=target_user.id,
            community_id=community.id
        ).first()
        
        if not target_membership:
            return False, "User must be member to become moderator"
        
        if target_membership.is_banned:
            return False, "Cannot make banned user a moderator"
        
        return True, None
    
    def _validate_remove_moderator(self, actor: User, target_user: User,
                                  community: Community) -> tuple[bool, Optional[str]]:
        """Validate removing a moderator"""
        membership = CommunityMember.query.filter_by(
            user_id=actor.id,
            community_id=community.id
        ).first()
        
        if not membership or not membership.is_admin:
            return False, "Only admins can remove moderators"
        
        # Cannot remove self as last admin
        if actor.id == target_user.id:
            admin_count = CommunityMember.query.filter_by(
                community_id=community.id,
                is_admin=True
            ).count()
            if admin_count <= 1:
                return False, "Cannot remove last admin"
        
        return True, None
    
    def _validate_ban_user(self, actor: User, target_user: User,
                          community: Community) -> tuple[bool, Optional[str]]:
        """Validate banning a user"""
        # Must be moderator
        if not self._is_moderator(actor, community):
            return False, "Only moderators can ban users"
        
        # Cannot ban moderators/admins
        target_membership = CommunityMember.query.filter_by(
            user_id=target_user.id,
            community_id=community.id
        ).first()
        
        if target_membership and (target_membership.is_moderator or target_membership.is_admin):
            return False, "Cannot ban moderators or admins"
        
        return True, None
    
    def _validate_update_community(self, actor: User, community: Community) -> tuple[bool, Optional[str]]:
        """Validate updating community settings"""
        membership = CommunityMember.query.filter_by(
            user_id=actor.id,
            community_id=community.id
        ).first()
        
        if not membership or not membership.is_admin:
            return False, "Only admins can update community settings"
        
        return True, None
    
    def _validate_delete_community(self, actor: User, community: Community) -> tuple[bool, Optional[str]]:
        """Validate deleting a community"""
        # Must be admin
        membership = CommunityMember.query.filter_by(
            user_id=actor.id,
            community_id=community.id
        ).first()
        
        if not membership or not membership.is_admin:
            return False, "Only admins can delete community"
        
        # Additional check - require site admin for large communities
        if community.members.count() > 1000:
            if not actor.is_site_admin:
                return False, "Large communities require site admin to delete"
        
        return True, None
    
    def get_user_permissions(self, user: User, community: Optional[Community] = None) -> List[Permission]:
        """Get list of permissions for user"""
        if user.is_site_admin:
            return list(Permission)  # All permissions
        
        if not community:
            return [Permission.CREATE_POST, Permission.CREATE_COMMENT]
        
        membership = CommunityMember.query.filter_by(
            user_id=user.id,
            community_id=community.id
        ).first()
        
        if not membership:
            return []
        
        if membership.is_banned:
            return []
        
        role = 'admin' if membership.is_admin else 'moderator' if membership.is_moderator else 'member'
        return self.role_permissions.get(role, [])