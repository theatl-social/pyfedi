from app import db, cache
from app.constants import ROLE_STAFF, ROLE_ADMIN
from app.models import UserBlock, NotificationSubscription, User
from app.constants import *
from app.utils import authorise_api_user, blocked_users

from flask import flash
from flask_babel import _
from flask_login import current_user

from sqlalchemy import text

# only called from API for now, but can be called from web using [un]block_another_user(user.id, SRC_WEB)

# user_id: the local, logged-in user
# person_id: the person they want to block

def block_another_user(person_id, src, auth=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    if user_id == person_id:
        if src == SRC_API:
            raise Exception('cannot_block_self')
        else:
            flash(_('You cannot block yourself.'), 'error')
            return

    role = db.session.execute(text('SELECT role_id FROM "user_role" WHERE user_id = :person_id'), {'person_id': person_id}).scalar()
    if role == ROLE_ADMIN or role == ROLE_STAFF:
        if src == SRC_API:
            raise Exception('cannot_block_admin_or_staff')
        else:
            flash(_('You cannot block admin or staff.'), 'error')
            return

    existing_block = UserBlock.query.filter_by(blocker_id=user_id, blocked_id=person_id).first()
    if not existing_block:
        block = UserBlock(blocker_id=user_id, blocked_id=person_id)
        db.session.add(block)
        db.session.execute(text('DELETE FROM "notification_subscription" WHERE entity_id = :current_user AND user_id = :user_id'),
                                        {'current_user': user_id, 'user_id': person_id})
        db.session.commit()

        cache.delete_memoized(blocked_users, user_id)

    # Nothing to fed? (Lemmy doesn't federate anything to the blocked person)

    if src == SRC_API:
        return user_id
    else:
        return              # let calling function handle confirmation flash message and redirect


def unblock_another_user(person_id, src, auth=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    if user_id == person_id:
        if src == SRC_API:
            raise Exception('cannot_unblock_self')
        else:
            flash(_('You cannot unblock yourself.'), 'error')
            return

    existing_block = UserBlock.query.filter_by(blocker_id=user_id, blocked_id=person_id).first()
    if existing_block:
        db.session.delete(existing_block)
        db.session.commit()

        cache.delete_memoized(blocked_users, user_id)

    # Nothing to fed? (Lemmy doesn't federate anything to the unblocked person)

    if src == SRC_API:
        return user_id
    else:
        return              # let calling function handle confirmation flash message and redirect


def toggle_user_notification(person_id: int, src, auth=None):
    # Toggle whether the current user is subscribed to notifications for activity from another user
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    person = User.query.filter_by(id=person_id).one()

    existing_notification = NotificationSubscription.query.filter(NotificationSubscription.entity_id == person.id,
                                                                  NotificationSubscription.user_id == user_id,
                                                                  NotificationSubscription.type == NOTIF_USER).first()
    if existing_notification:
        db.session.delete(existing_notification)
        db.session.commit()
    else:   # no subscription yet, so make one
        if person.id != user_id and not person.has_blocked_user(user_id):
            new_notification = NotificationSubscription(name=person.display_name(), user_id=user_id,
                                                        entity_id=person.id, type=NOTIF_USER)
            db.session.add(new_notification)
            db.session.commit()

    if src == SRC_API:
        return user_id
    else:
        return render_template('user/_notification_toggle.html', user=user)
