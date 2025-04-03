from app import cache, db
from app.models import InstanceBlock
from app.utils import authorise_api_user, blocked_instances
from app.constants import *

from flask import flash
from flask_babel import _
from flask_login import current_user


def block_remote_instance(instance_id, src, auth=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    if instance_id == 1:
        if src == SRC_API:
            raise Exception('cannot_block_local_instance')
        else:
            flash(_('You cannot block the local instance.'), 'error')
            return

    existing = InstanceBlock.query.filter_by(user_id=user_id, instance_id=instance_id).first()
    if not existing:
        db.session.add(InstanceBlock(user_id=user_id, instance_id=instance_id))
        db.session.commit()

        cache.delete_memoized(blocked_instances, user_id)

    if src == SRC_API:
        return user_id
    else:
        return              # let calling function handle confirmation flash message and redirect


def unblock_remote_instance(instance_id, src, auth=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    existing = InstanceBlock.query.filter_by(user_id=user_id, instance_id=instance_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

        cache.delete_memoized(blocked_instances, user_id)

    if src == SRC_API:
        return user_id
    else:
        return              # let calling function handle confirmation flash message and redirect
