from sqlalchemy import desc, asc, delete, update

from app import db
from app.api.alpha.views import registration_view
from app.utils import authorise_api_user, user_access, finalize_user_setup
from app.email import send_registration_approved_email
from app.models import utcnow, UserRegistration, User, Notification


def get_registration_list(auth, data):
    user = authorise_api_user(auth, return_type='model')
    
    if not user_access("approve registrations", user.id):
        raise Exception("Insufficient permissions to manage registrations")
    
    limit = data["limit"] if "limit" in data else 30
    page = data["page"] if "page" in data else 1
    pending_only = data["pending_only"] if "pending_only" in data else True
    sort = data["sort"] if "sort" in data else "New"

    if pending_only and sort == "New":
        registrations = UserRegistration.query.filter_by(status=0).order_by(desc(UserRegistration.created_at))
    elif pending_only and sort == "Old":
        registrations = UserRegistration.query.filter_by(status=0).order_by(asc(UserRegistration.created_at))
    elif sort == "New":
        registrations = UserRegistration.query.order_by(desc(UserRegistration.created_at))
    else:
        registrations = UserRegistration.query.order_by(asc(UserRegistration.created_at))
    
    registrations = registrations.paginate(page=page, per_page=limit, error_out=False)

    registration_list = []
    for registration in registrations:
        registration_list.append(registration_view(registration))
    
    return {"registrations": registration_list}


def put_registration_approve(auth, data):
    user = authorise_api_user(auth, return_type='model')
    
    if not user_access("approve registrations", user.id):
        raise Exception("Insufficient permissions to manage registrations")
    
    new_user_id = data["user_id"]
    approve = data["approve"]
    
    new_user = User.query.get(new_user_id)
    registration = UserRegistration.query.filter_by(status=0, user_id=new_user_id).first()

    if not registration:
        raise Exception("Problem finding registration for this user")

    if approve:
        # Registration approved
        registration.status = 1
        registration.approved_at = utcnow()
        registration.approved_by = user.id
        db.session.commit()
        if new_user.verified:
            finalize_user_setup(new_user)
            send_registration_approved_email(new_user)
    else:
        # Registration denied
        # remove the registration attempt
        db.session.delete(registration)

        # remove notifications caused by the registration attempt
        notifications = db.session.execute(
            delete(Notification)
            .where(Notification.author_id == new_user.id)
            .returning(Notification.user_id, Notification.read)
        ).all()
        unread_notification_users = [n.user_id for n in notifications if not n.read]
        db.session.execute(
            update(User)
            .where(User.id.in_(unread_notification_users))
            .values({User.unread_notifications: User.unread_notifications - 1})
        )

        # remove the user from the db so the username is available again
        new_user.deleted = True
        new_user.delete_dependencies()
        db.session.delete(new_user)

        # save that to the db
        db.session.commit()