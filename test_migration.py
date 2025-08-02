#!/usr/bin/env python
"""Test migration and database setup"""
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from flask import g
from test_config import TestConfig

app = create_app(TestConfig)

with app.app_context():
    # Create tables directly instead of running migrations
    print("Creating database tables...")
    try:
        # Drop all tables first
        db.drop_all()
        # Create all tables
        db.create_all()
        print("✓ Database tables created successfully")
    except Exception as e:
        print(f"✗ Failed to create tables: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Try to set up basic test data
    from app.models import Site, Role, RolePermission, User, Instance, Community
    from app.activitypub.signature import generate_rsa_keypair
    
    print("\nCreating test data...")
    
    # Create roles
    roles_data = [
        ('Anonymous user', 0, []),
        ('Authenticated user', 1, []),
        ('Staff', 2, ['approve registrations', 'ban users', 'administer all communities', 'administer all users']),
        ('Admin', 3, ['approve registrations', 'change user roles', 'ban users', 'manage users', 'change instance settings', 'administer all communities', 'administer all users', 'edit cms pages'])
    ]
    
    for name, weight, permissions in roles_data:
        role = Role.query.filter_by(name=name).first()
        if not role:
            role = Role(name=name, weight=weight)
            for perm in permissions:
                role.permissions.append(RolePermission(permission=perm))
            db.session.add(role)
    
    # Create Site
    site = Site.query.get(1)
    if not site:
        site = Site(
            id=1,
            name='Test Site',
            description='Test site for PyFedi',
            registration_mode='Open',
            enable_downvotes=True,
            enable_nsfw=False,
            enable_nsfl=False,
            community_creation_admin_only=False,
            reports_email_admins=True,
            application_question='',
            default_theme='',
            default_filter='',
            allow_or_block_list=0,
            log_activitypub_json=False
        )
        private_key, public_key = generate_rsa_keypair()
        site.private_key = private_key
        site.public_key = public_key
        db.session.add(site)
    
    # Create local instance
    instance = Instance.query.get(1)
    if not instance:
        instance = Instance(
            id=1,
            domain='test.local',
            software='pyfedi',
            version='1.0.0'
        )
        db.session.add(instance)
    
    # Create test user
    user = User.query.get(1)
    if not user:
        user = User(
            id=1,
            user_name='testuser',
            email='test@example.com',
            ap_profile_id='https://test.local/u/testuser',
            instance_id=1,
            verified=True
        )
        private_key, public_key = generate_rsa_keypair()
        user.private_key = private_key
        user.public_key = public_key
        user.set_password('password123')
        db.session.add(user)
    
    # Create test community
    community = Community.query.filter_by(name='testcommunity').first()
    if not community:
        community = Community(
            name='testcommunity',
            title='Test Community',
            description='A test community',
            ap_profile_id='https://test.local/c/testcommunity',
            instance_id=1,
            user_id=1
        )
        private_key, public_key = generate_rsa_keypair()
        community.private_key = private_key
        community.public_key = public_key
        db.session.add(community)
    
    try:
        db.session.commit()
        print("✓ Test data created successfully")
    except Exception as e:
        print(f"✗ Failed to create test data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Now test the API
    print("\nTesting API...")
    g.site = site
    
    from app.api.alpha.utils.site import get_site
    try:
        result = get_site(None)
        print("✓ API get_site() succeeded")
        print(f"  Site name: {result['site_view']['site']['name']}")
    except Exception as e:
        print(f"✗ API get_site() failed: {e}")
        import traceback
        traceback.print_exc()

print("\nAll tests completed!")