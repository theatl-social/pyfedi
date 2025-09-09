from flask import g, request
from flask_babel import _
from flask_babel import lazy_gettext as _l
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    FileField,
    HiddenField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    ValidationError,
)

from app import db


class AddTestCommunities(FlaskForm):
    communities_submit = SubmitField(_l("Populate Communities"))


class AddTestTopics(FlaskForm):
    topics_submit = SubmitField(_l("Populate Topics"))


class DeleteTestCommunities(FlaskForm):
    delete_communities_submit = SubmitField(_l("Delete Communities"))


class DeleteTestTopics(FlaskForm):
    delete_topics_submit = SubmitField(_l("Delete Topics"))
