from flask import render_template
from app import db
from app.errors import bp


# 404 error handler removed because a lot of 404s are just images in /static/* and it doesn't make sense to waste cpu cycles presenting a nice page.
# Also rendering a page requires populating g.site which means hitting the DB.
# @bp.app_errorhandler(404)
# def not_found_error(error):
#     return render_template('errors/404.html'), 404


@bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500
