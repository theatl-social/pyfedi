#!/usr/bin/env python
import os
from app import celery, create_app


app = create_app()
if not app.debug:
    os.environ['DATABASE_URL'] = 'postgresql+psycopg2://pyfedi:pyfedi@127.0.0.1/pyfedi'
    os.environ['SERVER_NAME'] = 'piefed.ngrok.app'

app.app_context().push()

from app.shared.tasks import maintenance
from app.shared.tasks import follows, likes, notes, deletes, flags, pages, locks, adds, removes, groups, users, blocks