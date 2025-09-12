#!/usr/bin/env python3
"""
Complete User Setup Script for PieFed

This script completes the setup process for partially configured users,
ensuring they have all necessary fields and approvals to function properly.

Usage:
    python complete_user_setup.py <username>
    python complete_user_setup.py --help

This script MUST be run from the terminal on the actual server running PieFed.
It requires direct filesystem access and database connections.

What this script does:
1. Finds user by username
2. Checks what setup steps are missing
3. Completes user registration approval workflow
4. Generates ActivityPub keys and URLs 
5. Sets all necessary flags for full functionality
6. Provides detailed output of what was fixed

Author: Generated for PieFed private registration fixes
"""

import sys
import os
import argparse
from datetime import datetime

def setup_flask_app():
    """Initialize Flask app context for database access"""
    # Add the current directory to Python path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from app import create_app, db
        from app.models import User, UserRegistration, utcnow
        from app.utils import finalize_user_setup
        
        app = create_app()
        
        return app, db, User, UserRegistration, utcnow, finalize_user_setup
    except ImportError as e:
        print(f"❌ Error importing PieFed modules: {e}")
        print("   Make sure you're running this script from the PieFed root directory")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error setting up Flask app: {e}")
        sys.exit(1)

def check_user_setup_status(user):
    """Analyze what setup steps are missing for a user"""
    issues = []
    fixes_needed = []
    
    # Check approval status
    if user.waiting_for_approval():
        issues.append("❌ User is waiting for approval")
        fixes_needed.append("create_approval_record")
    else:
        print("✅ User approval status: OK")
    
    # Check verification status  
    if not user.verified:
        issues.append("❌ User email not verified")
        fixes_needed.append("verify_email")
    else:
        print("✅ User verification status: OK")
        
    # Check ActivityPub keys
    if not user.private_key or not user.public_key:
        issues.append("❌ Missing ActivityPub keys")
        fixes_needed.append("generate_keys")
    else:
        print("✅ ActivityPub keys: OK")
        
    # Check ActivityPub URLs
    if not user.ap_profile_id or not user.ap_public_url or not user.ap_inbox_url:
        issues.append("❌ Missing ActivityPub profile URLs")
        fixes_needed.append("set_activitypub_urls")
    else:
        print("✅ ActivityPub URLs: OK")
        
    # Check basic user flags
    if user.deleted:
        issues.append("❌ User is marked as deleted")
        fixes_needed.append("undelete_user")
    else:
        print("✅ User deletion status: OK")
        
    if user.banned:
        issues.append("❌ User is banned")
        fixes_needed.append("unban_user")
    else:
        print("✅ User ban status: OK")
        
    return issues, fixes_needed

def apply_fixes(user, fixes_needed, db, UserRegistration, utcnow, finalize_user_setup):
    """Apply the necessary fixes to complete user setup"""
    fixes_applied = []
    
    if "create_approval_record" in fixes_needed:
        # Create approved UserRegistration record
        application = UserRegistration(
            user_id=user.id,
            answer='Setup completed by admin script',
            status=1,  # 1 = approved
            approved_at=utcnow(),
            approved_by=1  # System/admin approval
        )
        db.session.add(application)
        fixes_applied.append("✅ Created approved registration record")
        
    if "undelete_user" in fixes_needed:
        user.deleted = False
        fixes_applied.append("✅ Unmarked user as deleted")
        
    if "unban_user" in fixes_needed:
        user.banned = False
        user.banned_until = None
        fixes_applied.append("✅ Unbanned user")
        
    # Always run finalize_user_setup if any of these fixes are needed
    if any(fix in fixes_needed for fix in ["verify_email", "generate_keys", "set_activitypub_urls"]):
        finalize_user_setup(user)
        fixes_applied.append("✅ Completed user finalization (keys, URLs, verification)")
    
    return fixes_applied

def main():
    parser = argparse.ArgumentParser(
        description="Complete setup for partially configured PieFed users",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python complete_user_setup.py johndoe
  python complete_user_setup.py --check-only testuser
        """
    )
    
    parser.add_argument(
        "username", 
        help="Username of the user to complete setup for"
    )
    
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check what needs to be fixed, don't apply fixes"
    )
    
    parser.add_argument(
        "--force",
        action="store_true", 
        help="Apply fixes even if user appears to be properly configured"
    )
    
    args = parser.parse_args()
    
    print("🔧 PieFed User Setup Completion Script")
    print("=" * 50)
    print(f"Target user: {args.username}")
    print(f"Check-only mode: {args.check_only}")
    print()
    
    # Security check - only run on actual server
    if not os.path.exists("app") or not os.path.exists("config.py"):
        print("❌ ERROR: This script must be run from the PieFed root directory")
        print("   Make sure you're on the actual server running PieFed")
        sys.exit(1)
    
    # Setup Flask app and imports
    app, db, User, UserRegistration, utcnow, finalize_user_setup = setup_flask_app()
    
    with app.app_context():
        # Find the user
        user = User.query.filter_by(user_name=args.username).first()
        if not user:
            print(f"❌ ERROR: User '{args.username}' not found")
            sys.exit(1)
            
        print(f"✅ Found user: {user.user_name} (ID: {user.id})")
        print(f"   Email: {user.email}")
        print(f"   Created: {user.created}")
        print()
        
        # Check current status
        print("🔍 Checking user setup status...")
        issues, fixes_needed = check_user_setup_status(user)
        
        if not issues:
            print()
            print("🎉 User is already properly configured!")
            if not args.force:
                print("   Use --force to apply setup anyway")
                sys.exit(0)
            else:
                print("   --force specified, applying setup anyway...")
        else:
            print()
            print("⚠️  Issues found:")
            for issue in issues:
                print(f"   {issue}")
        
        if args.check_only:
            print()
            print("🔍 Check-only mode - no changes made")
            if fixes_needed:
                print("   Fixes that would be applied:")
                for fix in fixes_needed:
                    print(f"   - {fix}")
            sys.exit(0)
        
        # Apply fixes
        print()
        print("🔧 Applying fixes...")
        
        try:
            fixes_applied = apply_fixes(user, fixes_needed, db, UserRegistration, utcnow, finalize_user_setup)
            
            # Commit changes
            db.session.commit()
            
            print()
            print("✅ Setup completed successfully!")
            print("   Fixes applied:")
            for fix in fixes_applied:
                print(f"   {fix}")
                
            print()
            print("🎉 User is now fully configured and ready to use!")
            print(f"   User {args.username} can now:")
            print("   • Log in to PieFed")
            print("   • Participate in communities") 
            print("   • Use ActivityPub federation")
            print("   • Access all platform features")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ ERROR applying fixes: {e}")
            print("   No changes were made to the database")
            sys.exit(1)

if __name__ == "__main__":
    main()