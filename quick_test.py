#!/usr/bin/env python
"""Quick test to find the next error"""
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from flask import g

app = create_app()

with app.app_context():
    # Set up g.site
    from app.models import Site
    site = Site.query.get(1)
    if site:
        g.site = site
    
    # Try to run the problematic part of the test
    from app.api.alpha.utils.site import get_site
    
    try:
        anon_response = get_site(None)
        print("Success! get_site(None) returned:", type(anon_response))
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()