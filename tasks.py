from .celery import celery_app

@celery_app.task
def run_remove_orphan_files():
    from app.admin.util import remove_orphan_files
    remove_orphan_files()

@celery_app.task
def run_send_missed_notifs():
    from app.email import send_missed_notifs
    send_missed_notifs()

@celery_app.task
def run_process_email_bounces():
    from app.email import process_email_bounces
    process_email_bounces()

@celery_app.task
def run_clean_up_old_activities():
    from app.utils import clean_up_old_activities
    clean_up_old_activities()

@celery_app.task
def run_send_queue():
    from app.utils import send_queue
    send_queue()
