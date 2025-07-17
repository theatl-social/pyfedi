import os
from celery import Celery
from celery.schedules import crontab

REDIS_SERVER = os.environ.get("REDIS_SERVER", "localhost")
REDIS_URL = f"redis://{REDIS_SERVER}:6379/0"

celery_app = Celery(
    'pyfedi',
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    timezone='UTC',
    enable_utc=True,
    beat_schedule={
        'periodic_remove_orphan_files': {
            'task': 'tasks.run_remove_orphan_files',
            'schedule': crontab(minute=0, hour=3),  # daily at 3am
        },
        'periodic_send_missed_notifs': {
            'task': 'tasks.run_send_missed_notifs',
            'schedule': crontab(minute='*/10'),  # every 10 minutes
        },
        'periodic_process_email_bounces': {
            'task': 'tasks.run_process_email_bounces',
            'schedule': crontab(minute=15, hour='*'),  # hourly at :15
        },
        'periodic_clean_up_old_activities': {
            'task': 'tasks.run_clean_up_old_activities',
            'schedule': crontab(minute=0, hour=4),  # daily at 4am
        },
        'periodic_send_queue': {
            'task': 'tasks.run_send_queue',
            'schedule': crontab(minute='*/5'),  # every 5 minutes
        },
    }
)
