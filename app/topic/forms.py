from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class SuggestTopicsForm(FlaskForm):
    topic_name = TextAreaField(
        _l("New topic name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        render_kw={"placeholder": _l("New topic name here...")},
    )
    communities_for_topic = TextAreaField(
        _l("Suggested communities"),
        validators=[Optional(), Length(max=5000)],
        render_kw={"placeholder": _l("Comma seperated list of community suggestions")},
    )
    submit = SubmitField(_l("Submit"))
