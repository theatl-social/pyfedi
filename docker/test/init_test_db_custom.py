"""
Custom database initialization for testing
Handles the case where there are views that depend on tables
"""
import sys
import os
sys.path.insert(0, '/app/docker/test')
from test_env import TestConfig
sys.path.insert(0, '/app')
from app import create_app, db
from app.activitypub.signature import RsaKeys
from app.models import Site, Instance, Settings, Language, Role, RolePermission, User
from flask import json
from datetime import datetime
import uuid
from sqlalchemy import text

app = create_app(TestConfig)

with app.app_context():
    # Check if database is already initialized
    try:
        existing_site = Site.query.first()
        if existing_site:
            print("Database already initialized, skipping...")
            sys.exit(0)
    except:
        pass  # Table might not exist yet
    
    # Drop views first to avoid dependency issues
    try:
        db.session.execute(text('DROP VIEW IF EXISTS ap_request_combined CASCADE'))
        db.session.execute(text('DROP VIEW IF EXISTS ap_request_summary CASCADE'))
        db.session.commit()
    except:
        db.session.rollback()
    
    # Now we can safely drop and recreate tables
    try:
        db.drop_all()
    except:
        # If drop fails, continue anyway
        pass
    
    db.configure_mappers()
    db.create_all()
    
    # Generate site keys
    private_key, public_key = RsaKeys.generate_keypair()
    
    # Create site
    site = Site(
        name="PyFedi Test Instance",
        description='Test instance for security testing',
        public_key=public_key,
        private_key=private_key,
        language_id=2
    )
    db.session.add(site)
    
    # Create local instance
    db.session.add(Instance(
        domain=app.config['SERVER_NAME'],
        software='PieFed'
    ))
    
    # Add settings
    db.session.add(Settings(name='allow_nsfw', value=json.dumps(False)))
    db.session.add(Settings(name='allow_nsfl', value=json.dumps(False)))
    db.session.add(Settings(name='allow_dislike', value=json.dumps(True)))
    db.session.add(Settings(name='allow_local_image_posts', value=json.dumps(True)))
    db.session.add(Settings(name='allow_remote_image_posts', value=json.dumps(True)))
    db.session.add(Settings(name='federation', value=json.dumps(True)))
    
    # Initial languages
    db.session.add(Language(name='Undetermined', code='und'))
    db.session.add(Language(code='en', name='English'))
    
    # Initial roles
    anon_role = Role(name='Anonymous user', weight=0)
    db.session.add(anon_role)
    
    auth_role = Role(name='Authenticated user', weight=1)
    db.session.add(auth_role)
    
    staff_role = Role(name='Staff', weight=2)
    staff_role.permissions.append(RolePermission(permission='approve registrations'))
    staff_role.permissions.append(RolePermission(permission='ban users'))
    staff_role.permissions.append(RolePermission(permission='administer all communities'))
    staff_role.permissions.append(RolePermission(permission='administer all users'))
    db.session.add(staff_role)
    
    admin_role = Role(name='Admin', weight=3)
    admin_role.permissions.append(RolePermission(permission='approve registrations'))
    admin_role.permissions.append(RolePermission(permission='change user roles'))
    admin_role.permissions.append(RolePermission(permission='ban users'))
    admin_role.permissions.append(RolePermission(permission='manage users'))
    admin_role.permissions.append(RolePermission(permission='change instance settings'))
    admin_role.permissions.append(RolePermission(permission='administer all communities'))
    admin_role.permissions.append(RolePermission(permission='administer all users'))
    admin_role.permissions.append(RolePermission(permission='edit cms pages'))
    db.session.add(admin_role)
    
    # Create test admin user
    private_key, public_key = RsaKeys.generate_keypair()
    admin_user = User(
        user_name='admin',
        title='Test Admin',
        email='admin@test.local',
        verification_token=str(uuid.uuid4()),
        instance_id=1,
        email_unread_sent=False,
        private_key=private_key,
        public_key=public_key,
        alt_user_name='admin_alt_' + str(uuid.uuid4())[:8]
    )
    admin_user.set_password('testpassword123')
    admin_user.roles.append(admin_role)
    admin_user.verified = True
    admin_user.last_seen = datetime.utcnow()
    # Don't set AP URLs - let the app handle them
    db.session.add(admin_user)
    
    db.session.commit()
    print("Test database initialized successfully!")