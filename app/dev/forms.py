from flask import request, g
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    SubmitField,
    TextAreaField,
    BooleanField,
    HiddenField,
    SelectField,
    FileField,
)
from wtforms.validators import (
    ValidationError,
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
)
from flask_babel import _, lazy_gettext as _l

from app import db


class AddTestCommunities(FlaskForm):
    communities_submit = SubmitField(_l("Populate Communities"))


class AddTestTopics(FlaskForm):
    topics_submit = SubmitField(_l("Populate Topics"))


class DeleteTestCommunities(FlaskForm):
    delete_communities_submit = SubmitField(_l("Delete Communities"))


class DeleteTestTopics(FlaskForm):
    delete_topics_submit = SubmitField(_l("Delete Topics"))
