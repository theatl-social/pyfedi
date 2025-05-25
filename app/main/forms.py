from flask_wtf import FlaskForm
from wtforms import TextAreaField, SubmitField, BooleanField, StringField, HiddenField
from wtforms.fields.choices import SelectField
from wtforms.validators import DataRequired, Length, ValidationError
from flask_babel import _, lazy_gettext as _l


class ShareLinkForm(FlaskForm):
    which_community = SelectField(_l('Community to post this link to'), validators=[DataRequired()], coerce=int, render_kw={'class': 'form-select'})
    submit = SubmitField(_l('Next'))
