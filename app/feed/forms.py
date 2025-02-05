from flask import request, g
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, HiddenField, SelectField, FileField, \
    DateField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo, Length, Regexp, Optional
from wtforms.fields.choices import SelectMultipleField
from app.models import Feed, utcnow
from flask_babel import _, lazy_gettext as _l


class AddFeedForm(FlaskForm):
    feed_name = StringField(_l('Name'), validators=[DataRequired()])
    url = StringField(_l('Url'))
    description = TextAreaField(_l('Description'))
    icon_file = FileField(_l('Icon image'), render_kw={'accept': 'image/*'})
    banner_file = FileField(_l('Banner image'), render_kw={'accept': 'image/*'})
    nsfw = BooleanField('NSFW')
    nsfl = BooleanField('NSFL')
    public = BooleanField('Make Feed Public')
    submit = SubmitField(_l('Create'))

    def validate(self, extra_validators=None):
        if not super().validate():
            return False
        if self.url.data.strip() == '':
            self.url.errors.append(_l('Url is required.'))
            return False
        else:
            if '-' in self.url.data.strip():
                self.url.errors.append(_l('- cannot be in Url. Use _ instead?'))
                return False
            community = Feed.query.filter(Feed.name == self.url.data.strip().lower(), Feed.ap_id == None).first()
            if community is not None:
                self.url.errors.append(_l('A Feed with this url already exists.'))
                return False
        return True

class EditFeedForm(FlaskForm):
    feed_name = StringField(_l('Name'), validators=[DataRequired()])
    url = StringField(_l('Url'))
    description = TextAreaField(_l('Description'))
    icon_file = FileField(_l('Icon image'), render_kw={'accept': 'image/*'})
    banner_file = FileField(_l('Banner image'), render_kw={'accept': 'image/*'})
    nsfw = BooleanField('NSFW')
    nsfl = BooleanField('NSFL')
    public = BooleanField('Make Feed Public')
    submit = SubmitField(_l('Save'))

