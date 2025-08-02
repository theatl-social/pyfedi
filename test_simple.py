#!/usr/bin/env python
"""Simple test without database creation"""
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set test environment before importing app
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
os.environ['TESTING'] = '1'

from flask import Flask, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# Create minimal Flask app without all the extensions
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SECRET_KEY'] = 'test-secret'
app.config['TESTING'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

with app.app_context():
    # Just test the API logic without database
    print("Testing API logic...")
    
    # Create a minimal Site object
    class Site:
        def __init__(self):
            self.id = 1
            self.name = 'Test Site'
            self.description = 'Test site for PyFedi'
            self.registration_mode = 'Open'
            self.enable_downvotes = True
            self.enable_nsfw = False
            self.enable_nsfl = False
            self.community_creation_admin_only = False
            self.reports_email_admins = True
            self.application_question = ''
            self.default_theme = ''
            self.default_filter = ''
            self.allow_or_block_list = 0
            self.log_activitypub_json = False
            self.enable_gif_reply_rep_decrease = False
            self.enable_chan_image_filter = False
            self.enable_this_comment_filter = False
            self.allow_local_image_posts = True
            self.remote_image_cache_days = 30
            self.logo = ''
            self.logo_180 = ''
            self.logo_152 = ''
            self.logo_32 = ''
            self.logo_16 = ''
            self.contact_email = ''
            self.show_inoculation_block = True
            self.private_instance = False
            self.version = '1.0.0'
            self.created_at = None
    
    g.site = Site()
    
    # Import after setting up g.site
    from app.api.alpha.utils.site import get_site
    
    try:
        result = get_site(None)
        print("✓ API get_site() succeeded")
        print(f"  Site name: {result['site_view']['site']['name']}")
        print(f"  Version: {result['version']}")
    except Exception as e:
        print(f"✗ API get_site() failed: {e}")
        import traceback
        traceback.print_exc()

print("\nTest completed!")