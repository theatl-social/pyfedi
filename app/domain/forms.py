from flask_wtf import FlaskForm
from flask_babel import _, lazy_gettext as _l
from wtforms import StringField, SubmitField


class PostWarningForm(FlaskForm):
    post_warning = StringField(_l('Warning on posts'))
    submit = SubmitField(_l('Save'))
