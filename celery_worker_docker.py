#!/usr/bin/env python
import os
from app import celery, create_app

app = create_app()
app.app_context().push()

# Import all task modules to register them with Celery
from app.shared.tasks import maintenance
from app.shared.tasks import follows, likes, notes, deletes, flags, pages, locks, adds, removes, groups, users, blocks
