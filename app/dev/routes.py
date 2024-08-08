from flask import request, flash, json, url_for, current_app, redirect, g, abort
from flask_login import login_required, current_user
from flask_babel import _
from sqlalchemy import desc, or_, and_, text

from app import db, celery
from app.dev.forms import AddTestCommunities
# from app.chat.forms import AddReply, ReportConversationForm
# from app.chat.util import send_message
from app.models import Site, User, Community
# from app.user.forms import ReportUserForm
from app.utils import render_template, moderating_communities, joined_communities, menu_topics
from app.dev import bp


# use this to populate communities in the database
@bp.route('/dev/populate-communities', methods=['GET', 'POST'])
@login_required
def populate_communities():
    form = AddTestCommunities()
    if form.validate_on_submit():
        flash(_('form sumbit button pressed'))
        return redirect(url_for('dev.populate_communities'))
    else:
        return render_template('dev/populate_communities.html', form=form)
