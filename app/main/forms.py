from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import HiddenField, SubmitField
from wtforms.fields.choices import SelectField
from wtforms.validators import DataRequired


class ShareLinkForm(FlaskForm):
    which_community = SelectField(
        _l("Community to post this link to"),
        validators=[DataRequired()],
        coerce=int,
        render_kw={"class": "form-select"},
    )
    submit = SubmitField(_l("Next"))


class ContentWarningForm(FlaskForm):
    next = HiddenField()
    submit = SubmitField(_l("Continue"))
