from flask import current_app

from app.models import votes_cast_today


def vote_quota_exceeded(user_id: int) -> bool:
    quota = current_app.config["VOTE_QUOTA"]
    return quota != 0 and votes_cast_today(user_id) > quota
