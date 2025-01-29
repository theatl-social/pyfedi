from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import ValidationError, DataRequired, Length, Optional
from flask_babel import _, lazy_gettext as _l


class SuggestTopicsForm(FlaskForm):
    topic_name = TextAreaField(_l('New topic name'), validators=[DataRequired(), Length(min=1, max=100)],
                               render_kw={'placeholder': _l('New topic name here...')})
    communities_for_topic = TextAreaField(_l('Suggested communities'), validators=[Optional(), Length(max=5000)],
                                          render_kw={'placeholder': _l('Comma seperated list of community suggestions')})
    submit = SubmitField(_l('Submit'))
