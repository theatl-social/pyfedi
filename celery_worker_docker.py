#!/usr/bin/env python
import os
from app import celery, create_app

app = create_app()
app.app_context().push()

# Import all task modules to register them with Celery
from app.shared.tasks import maintenance
from app.shared.tasks import follows, likes, notes, deletes, flags, pages, locks, adds, removes, groups, users, blocks
from app.activitypub import signature  # Import signature module which contains post_request task

# Log all registered tasks at startup
print("=== Celery Worker Starting ===")
print(f"Registered tasks: {sorted(celery.tasks.keys())}")
print(f"Looking for post_request task: {'app.activitypub.signature.post_request' in celery.tasks}")
print("=== End Celery Worker Startup ===")
