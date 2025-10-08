#!/usr/bin/env python
import os
from app import celery, create_app, db
from celery.signals import task_prerun, task_postrun


app = create_app()
if not app.debug:
    os.environ['DATABASE_URL'] = 'postgresql+psycopg2://pyfedi:pyfedi@127.0.0.1/pyfedi'
    os.environ['SERVER_NAME'] = 'piefed.ngrok.app'

app.app_context().push()

from app.shared.tasks import maintenance
from app.shared.tasks import follows, likes, notes, deletes, flags, pages, locks, adds, removes, groups, users, blocks

# Ensure fresh database session for each Celery task
@task_prerun.connect
def celery_task_prerun(*args, **kwargs):
    """Remove any existing database session before task starts to prevent stale connections"""
    db.session.remove()

@task_postrun.connect
def celery_task_postrun(*args, **kwargs):
    """Clean up database session after task completes"""
    db.session.remove()