from flask import render_template
from app import db
from app.errors import bp


# 404 error handler removed because a lot of 404s are just images in /static/* and it doesn't make sense to waste cpu cycles presenting a nice page.
# Also rendering a page requires populating g.site which means hitting the DB.
# @bp.app_errorhandler(404)
# def not_found_error(error):
#     return render_template('errors/404.html'), 404


@bp.app_errorhandler(500)
def internal_error_500(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500


@bp.app_errorhandler(401)
def internal_error_401(error):
    db.session.rollback()
    return render_template('errors/401.html'), 401


@bp.app_errorhandler(429)
def rate_limited_429(error):
    return render_template('errors/429.html', error=error), 429
