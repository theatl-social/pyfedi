from flask import request, g
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, HiddenField, SelectField, FileField, \
    DateField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo, Length, Regexp, Optional
from wtforms.fields.choices import SelectMultipleField
from app.models import Feed, utcnow, Community, User
from flask_babel import _, lazy_gettext as _l


class AddCopyFeedForm(FlaskForm):
    title = StringField(_l('Name'), validators=[DataRequired()])
    url = StringField(_l('Url'), validators=[Length(max=30)])
    description = TextAreaField(_l('Description'))
    parent_feed_id = SelectField(_l('Parent feed'), coerce=int, validators=[Optional()], render_kw={'class': 'form-select'})
    show_child_posts = BooleanField('Show posts from child feeds')
    communities = TextAreaField(_l('Communities'), validators=[DataRequired()], render_kw={'rows': 5})
    icon_file = FileField(_l('Icon image'), render_kw={'accept': 'image/*'})
    banner_file = FileField(_l('Banner image'), render_kw={'accept': 'image/*'})
    nsfw = BooleanField('NSFW')
    nsfl = BooleanField('NSFL')
    public = BooleanField('Public', default=True)
    is_instance_feed = BooleanField('Add to main menu')
    submit = SubmitField(_l('Save'))

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
            feed = Feed.query.filter(Feed.name == self.url.data.strip().lower()).first()
            if feed is not None:
                self.url.errors.append(_l('A Feed with this url already exists.'))
                return False
            community = Community.query.filter(Community.name == self.url.data.strip().lower(), Community.ap_id == None).first()
            if community is not None:
                self.url.errors.append(_l('A community with this url already exists.'))
                return False
            user = User.query.filter(func.lower(User.user_name) == func.lower(self.url.data.strip())).filter_by(ap_id=None).first()
            if user is not None:
                if user.deleted:
                    self.url.errors.append(_l('This name was used in the past and cannot be reused.'))
                else:
                    self.url.errors.append(_l('This name is in use already.'))
                return False
        
        input_communities = self.communities.data.strip().split('\n')
        for community_ap_id in input_communities:
            if not '@' in community_ap_id:
                self.communities.errors.append(_l('Please make sure each community is formatted as "community_name@instance.tld"'))
                return False
        return True    


class EditFeedForm(FlaskForm):
    feed_id = 0
    title = StringField(_l('Name'), validators=[DataRequired()])
    url = StringField(_l('Url'), validators=[Length(max=50)])
    description = TextAreaField(_l('Description'))
    parent_feed_id = SelectField(_l('Parent feed'), coerce=int, validators=[Optional()], render_kw={'class': 'form-select'})
    show_child_posts = BooleanField('Show posts from child feeds')
    communities = TextAreaField(_l('Communities'), validators=[DataRequired()], render_kw={'rows': 5})
    icon_file = FileField(_l('Icon image'), render_kw={'accept': 'image/*'})
    banner_file = FileField(_l('Banner image'), render_kw={'accept': 'image/*'})
    nsfw = BooleanField('NSFW')
    nsfl = BooleanField('NSFL')
    public = BooleanField('Public')
    is_instance_feed = BooleanField('Add to main menu')
    submit = SubmitField(_l('Save'))

    def validate(self, extra_validators=None):
        if not super().validate():
            return False
        feed = Feed.query.filter(Feed.name == self.url.data.strip().lower()).first()
        if feed is not None and feed.id != self.feed_id:
            self.url.errors.append(_l('Url is already used by another feed.'))
            return False
        
        input_communities = self.communities.data.strip().split('\n')
        for community_ap_id in input_communities:
            if not '@' in community_ap_id:
                self.communities.errors.append(_l('Please make sure each community is formatted as "community_name@instance.tld"'))
                return False
        return True


class SearchRemoteFeed(FlaskForm):
    address = StringField(_l('Feed address'), render_kw={'placeholder': 'e.g. https://server.name/f/feedname', 'autofocus': True}, validators=[DataRequired()])
    submit = SubmitField(_l('Search'))