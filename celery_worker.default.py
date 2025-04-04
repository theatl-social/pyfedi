#!/usr/bin/env python
import os

from celery import Celery

from app import celery, create_app


app = create_app()
if not app.debug:
    os.environ['DATABASE_URL'] = 'postgresql+psycopg2://pyfedi:pyfedi@127.0.0.1/pyfedi'
    os.environ['SERVER_NAME'] = 'piefed.ngrok.app'


# Create Celery and bind Flask context
def make_celery(app):
    celery = Celery(
        app.import_name,
        broker=app.config['CELERY_BROKER_URL'],
        backend=app.config.get('CELERY_RESULT_BACKEND')
    )
    celery.conf.update(app.config)

    return celery


celery = make_celery(app)

