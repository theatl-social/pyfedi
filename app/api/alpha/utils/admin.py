from flask import current_app
from sqlalchemy import desc, asc

from app.api.alpha.views import registration_view
from app.utils import authorise_api_user, user_access
from app.models import UserRegistration


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