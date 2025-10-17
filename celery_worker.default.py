#!/usr/bin/env python
import os
from app import celery, create_app, db
from celery.signals import worker_process_init, task_prerun, task_postrun


app = create_app()
if not app.debug:
    os.environ["DATABASE_URL"] = "postgresql+psycopg2://pyfedi:pyfedi@127.0.0.1/pyfedi"
    os.environ["SERVER_NAME"] = "piefed.ngrok.app"

app.app_context().push()

from app.shared.tasks import maintenance
from app.shared.tasks import (
    follows,
    likes,
    notes,
    deletes,
    flags,
    pages,
    locks,
    adds,
    removes,
    groups,
    users,
    blocks,
)


# Dispose of connection pool inherited from parent process after fork
@worker_process_init.connect
def init_celery_worker(**kwargs):
    """
    Called once when each Celery worker process starts (after fork).
    Disposes of the connection pool inherited from the parent process.

    This prevents the "PGRES_TUPLES_OK and no message from libpq" error
    caused by multiple processes sharing the same PostgreSQL connection
    file descriptors.

    Reference: https://docs.sqlalchemy.org/en/20/core/pooling.html#using-connection-pools-with-multiprocessing-or-os-fork
    """
    # close=False prevents closing parent process connections
    db.engine.dispose(close=False)


# Ensure fresh database session for each Celery task
@task_prerun.connect
def celery_task_prerun(*args, **kwargs):
    """Remove any existing database session before task starts to prevent stale connections"""
    db.session.remove()


@task_postrun.connect
def celery_task_postrun(*args, **kwargs):
    """Clean up database session after task completes"""
    db.session.remove()
