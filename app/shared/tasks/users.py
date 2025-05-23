from flask import current_app
from sqlalchemy import text

from app import celery, httpx_client, db
from app.models import UserRegistration
from app.utils import get_setting


@celery.task
def check_user_application(application_id):
    application = UserRegistration.query.get(application_id)
    if not application or not application.user:
        return

    num_banned = 0

    for domain in get_setting('ban_check_servers', 'piefed.social').split('\n'):
        if not domain.strip():
            continue

        try:
            uri = f'https://{domain.strip()}/api/is_ip_or_email_banned'
            data = {
                'ip_address': application.user.ip_address,
                'email': application.user.email
            }

            response = httpx_client.post(uri, data=data, timeout=5)

            if response.status_code == 200:
                result = response.json()
                if result.get('ip_address', False):
                    num_banned += 1
                if result.get('email', False):
                    num_banned += 1
        except Exception as e:
            current_app.logger.error(f"Error checking bans on {domain}: {str(e)}")
            continue

    if num_banned > 0:
        db.session.execute(text('UPDATE "user_registration" SET warning = :warning WHERE id = :id',
                                {'warning': f"{num_banned} instances have banned this account.", 'id': application_id}))
        db.session.commit()
