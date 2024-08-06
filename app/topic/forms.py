from flask import request
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, HiddenField, SelectField, FileField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo, Length, Optional
from flask_babel import _, lazy_gettext as _l
from app.utils import MultiCheckboxField

from app import db


class ChooseTopicsForm(FlaskForm):
    chosen_topics = MultiCheckboxField(_l('Choose some topics you are interested in'), coerce=int)
    submit = SubmitField(_l('Choose'))

class SuggestTopicsForm(FlaskForm):
    topic_name = TextAreaField(_l('New Topic Name'), validators=[DataRequired(), Length(min=1, max=100)], render_kw={'placeholder': 'Type a reply here...'})
    communities_for_topic = TextAreaField(_l('Suggested Communities'), validators=[DataRequired(), Length(min=1, max=5000)], render_kw={'placeholder': 'Comma seperated list of community suggestions'})
    submit = SubmitField(_l('Submit'))
