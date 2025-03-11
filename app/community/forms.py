from flask import request, g
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, HiddenField, SelectField, FileField, \
    DateField
from wtforms.fields.choices import SelectMultipleField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo, Length, Regexp, Optional
from flask_babel import _, lazy_gettext as _l

from app import db
from app.constants import DOWNVOTE_ACCEPT_ALL, DOWNVOTE_ACCEPT_MEMBERS, DOWNVOTE_ACCEPT_INSTANCE, \
    DOWNVOTE_ACCEPT_TRUSTED
from app.models import Community, utcnow
from app.utils import domain_from_url, MultiCheckboxField
from PIL import Image, ImageOps, UnidentifiedImageError
from io import BytesIO
import pytesseract


class AddCommunityForm(FlaskForm):
    community_name = StringField(_l('Name'), validators=[DataRequired()])
    url = StringField(_l('Url'))
    description = TextAreaField(_l('Description'))
    icon_file = FileField(_l('Icon image'), render_kw={'accept': 'image/*'})
    banner_file = FileField(_l('Banner image'), render_kw={'accept': 'image/*'})
    rules = TextAreaField(_l('Rules'))
    nsfw = BooleanField('NSFW')
    local_only = BooleanField('Local only')
    languages = SelectMultipleField(_l('Languages'), coerce=int, validators=[Optional()], render_kw={'class': 'form-select'})
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
            community = Community.query.filter(Community.name == self.url.data.strip().lower(), Community.ap_id == None).first()
            if community is not None:
                self.url.errors.append(_l('A community with this url already exists.'))
                return False
        return True


class EditCommunityForm(FlaskForm):
    title = StringField(_l('Title'), validators=[DataRequired()])
    description = TextAreaField(_l('Description'))
    icon_file = FileField(_l('Icon image'), render_kw={'accept': 'image/*'})
    banner_file = FileField(_l('Banner image'), render_kw={'accept': 'image/*'})
    rules = TextAreaField(_l('Rules'))
    nsfw = BooleanField(_l('Porn community'))
    local_only = BooleanField(_l('Only accept posts from current instance'))
    restricted_to_mods = BooleanField(_l('Only moderators can post'))
    new_mods_wanted = BooleanField(_l('New moderators wanted'))
    downvote_accept_modes = [(DOWNVOTE_ACCEPT_ALL, _l('Everyone')),
                             (DOWNVOTE_ACCEPT_MEMBERS, _l('Community members')),
                             (DOWNVOTE_ACCEPT_INSTANCE, _l('This instance')),
                             (DOWNVOTE_ACCEPT_TRUSTED, _l('Trusted instances')),

    ]
    downvote_accept_mode = SelectField(_l('Accept downvotes from'), coerce=int, choices=downvote_accept_modes, validators=[Optional()], render_kw={'class': 'form-select'})
    topic = SelectField(_l('Topic'), coerce=int, validators=[Optional()], render_kw={'class': 'form-select'})
    languages = SelectMultipleField(_l('Languages'), coerce=int, validators=[Optional()], render_kw={'class': 'form-select'})
    layouts = [('', _l('List')),
               ('masonry', _l('Masonry')),
               ('masonry_wide', _l('Wide masonry'))]
    default_layout = SelectField(_l('Layout'), coerce=str, choices=layouts, validators=[Optional()], render_kw={'class': 'form-select'})
    submit = SubmitField(_l('Save'))


class EditCommunityWikiPageForm(FlaskForm):
    title = StringField(_l('Title'), validators=[DataRequired()])
    slug = StringField(_l('Slug'), validators=[DataRequired()])
    body = TextAreaField(_l('Body'), render_kw={'rows': '10'})
    edit_options = [(0, _l('Mods and admins')),
                    (1, _l('Trusted accounts')),
                    (2, _l('Community members')),
                    (3, _l('Any account'))
    ]
    who_can_edit = SelectField(_l('Who can edit'), coerce=int, choices=edit_options, validators=[Optional()], render_kw={'class': 'form-select'})
    submit = SubmitField(_l('Save'))


class AddModeratorForm(FlaskForm):
    user_name = StringField(_l('User name'), validators=[DataRequired()])
    submit = SubmitField(_l('Find'))


class EscalateReportForm(FlaskForm):
    reason = StringField(_l('Amend the report description if necessary'), validators=[DataRequired()])
    submit = SubmitField(_l('Escalate report'))


class ResolveReportForm(FlaskForm):
    note = StringField(_l('Note for mod log'), validators=[Optional()])
    also_resolve_others = BooleanField(_l('Also resolve all other reports about the same thing.'), default=True)
    submit = SubmitField(_l('Resolve report'))


class SearchRemoteCommunity(FlaskForm):
    address = StringField(_l('Community address'), render_kw={'placeholder': 'e.g. !name@server', 'autofocus': True, 'autocomplete': 'off'}, validators=[DataRequired()])
    submit = SubmitField(_l('Search'))


class BanUserCommunityForm(FlaskForm):
    reason = StringField(_l('Reason'), render_kw={'autofocus': True}, validators=[DataRequired()])
    ban_until = DateField(_l('Ban until'), validators=[Optional()])
    delete_posts = BooleanField(_l('Also delete all their posts'))
    delete_post_replies = BooleanField(_l('Also delete all their comments'))
    submit = SubmitField(_l('Ban'))


class CreatePostForm(FlaskForm):
    communities = SelectField(_l('Community'), validators=[DataRequired()], coerce=int, render_kw={'class': 'form-select'})
    title = StringField(_l('Title'), validators=[DataRequired(), Length(min=3, max=255)])
    body = TextAreaField(_l('Body'), validators=[Optional(), Length(min=3, max=5000)], render_kw={'rows': 5})
    tags = StringField(_l('Tags'), validators=[Optional(), Length(min=3, max=5000)])
    sticky = BooleanField(_l('Sticky'))
    nsfw = BooleanField(_l('NSFW'))
    nsfl = BooleanField(_l('Gore/gross'))
    notify_author = BooleanField(_l('Notify about replies'))
    language_id = SelectField(_l('Language'), validators=[DataRequired()], coerce=int, render_kw={'class': 'form-select'})
    submit = SubmitField(_l('Save'))


class CreateDiscussionForm(CreatePostForm):
    pass


class CreateLinkForm(CreatePostForm):
    link_url = StringField(_l('URL'), validators=[DataRequired(), Regexp(r'^https?://', message='Submitted links need to start with "http://"" or "https://"')],
                           render_kw={'placeholder': 'https://...',
                                      'hx-get': '/community/check_url_already_posted',
                                      'hx-params': '*',
                                      'hx-target': '#urlUsed'})

    def validate(self, extra_validators=None) -> bool:
        domain = domain_from_url(self.link_url.data, create=False)
        if domain and domain.banned:
            self.link_url.errors.append(_l("Links to %(domain)s are not allowed.", domain=domain.name))
            return False
        return True


class CreateVideoForm(CreatePostForm):
    video_url = StringField(_l('URL'), validators=[DataRequired(), Regexp(r'^https?://', message='Submitted links need to start with "http://"" or "https://"')],
                           render_kw={'placeholder': 'https://...'})

    def validate(self, extra_validators=None) -> bool:
        domain = domain_from_url(self.video_url.data, create=False)
        if domain and domain.banned:
            self.video_url.errors.append(_l("Videos from %(domain)s are not allowed.", domain=domain.name))
            return False
        return True


class CreateImageForm(CreatePostForm):
    image_alt_text = StringField(_l('Alt text'), validators=[Optional(), Length(min=3, max=1500)])
    image_file = FileField(_l('Image'), validators=[DataRequired()], render_kw={'accept': 'image/*'})

    def validate(self, extra_validators=None) -> bool:
        uploaded_file = request.files['image_file']
        if uploaded_file and uploaded_file.filename != '' and not uploaded_file.filename.endswith('.svg'):
            Image.MAX_IMAGE_PIXELS = 89478485
            # Do not allow fascist meme content
            try:
                if '.avif' in uploaded_file.filename:
                    import pillow_avif
                image_text = pytesseract.image_to_string(Image.open(BytesIO(uploaded_file.read())).convert('L'))
            except FileNotFoundError:
                image_text = ''
            except UnidentifiedImageError:
                image_text = ''
            if 'Anonymous' in image_text and (
                    'No.' in image_text or ' N0' in image_text):  # chan posts usually contain the text 'Anonymous' and ' No.12345'
                self.image_file.errors.append(
                    "This image is an invalid file type.")  # deliberately misleading error message
                current_user.reputation -= 1
                db.session.commit()
                return False
        if self.communities:
            community = Community.query.get(self.communities.data)
            if community.is_local() and g.site.allow_local_image_posts is False:
                self.communities.errors.append(_l('Images cannot be posted to local communities.'))

        return True

class EditImageForm(CreateImageForm):
    image_file = FileField(_l('Replace Image'), validators=[DataRequired()], render_kw={'accept': 'image/*'})
    image_file = FileField(_l('Image'), validators=[Optional()], render_kw={'accept': 'image/*'})
    
    def validate(self, extra_validators=None) -> bool:
        if self.communities:
            community = Community.query.get(self.communities.data)
            if community.is_local() and g.site.allow_local_image_posts is False:
                self.communities.errors.append(_l('Images cannot be posted to local communities.'))

        return True

class CreatePollForm(CreatePostForm):
    mode = SelectField(_('Mode'), validators=[DataRequired()], choices=[('single', _l('Voters choose one option')), ('multiple', _l('Voters choose many options'))], render_kw={'class': 'form-select'})
    finish_choices=[
        ('30m', _l('30 minutes')),
        ('1h', _l('1 hour')),
        ('6h', _l('6 hours')),
        ('12h', _l('12 hours')),
        ('1d', _l('1 day')),
        ('3d', _l('3 days')),
        ('7d', _l('7 days')),
    ]
    finish_in = SelectField(_('End voting in'), validators=[DataRequired()], choices=finish_choices, render_kw={'class': 'form-select'})
    local_only = BooleanField(_l('Accept votes from this instance only'))
    choice_1 = StringField('Choice')    # intentionally left out of internationalization (no _l()) as this label is not used
    choice_2 = StringField('Choice')
    choice_3 = StringField('Choice')
    choice_4 = StringField('Choice')
    choice_5 = StringField('Choice')
    choice_6 = StringField('Choice')
    choice_7 = StringField('Choice')
    choice_8 = StringField('Choice')
    choice_9 = StringField('Choice')
    choice_10 = StringField('Choice')

    def validate(self, extra_validators=None) -> bool:
        choices_made = 0

        for i in range(1, 10):
            choice_data = getattr(self, f"choice_{i}").data.strip()
            if choice_data != '':
                choices_made += 1
        if choices_made == 0:
            self.choice_1.errors.append(_l('Polls need options for people to choose from'))
            return False
        elif choices_made <= 1:
            self.choice_2.errors.append(_l('Provide at least two choices'))
            return False
        return True


class ReportCommunityForm(FlaskForm):
    reason_choices = [('1', _l('Breaks instance rules')),
                      ('2', _l('Abandoned by moderators')),
                      ('3', _l('Cult')),
                      ('4', _l('Scam')),
                      ('5', _l('Alt-right pipeline')),
                      ('6', _l('Hate / genocide')),
                      ('7', _l('Other')),
                      ]
    reasons = MultiCheckboxField(_l('Reason'), choices=reason_choices)
    description = StringField(_l('More info'))
    report_remote = BooleanField('Also send report to originating instance')
    submit = SubmitField(_l('Report'))

    def reasons_to_string(self, reason_data) -> str:
        result = []
        for reason_id in reason_data:
            for choice in self.reason_choices:
                if choice[0] == reason_id:
                    result.append(str(choice[1]))
        return ', '.join(result)


class DeleteCommunityForm(FlaskForm):
    submit = SubmitField(_l('Delete community'))


class RetrieveRemotePost(FlaskForm):
    address = StringField(_l('Full URL'), render_kw={'placeholder': 'e.g. https://lemmy.world/post/123', 'autofocus': True}, validators=[DataRequired()])
    submit = SubmitField(_l('Retrieve'))


class InviteCommunityForm(FlaskForm):
    to = TextAreaField(_l('To'), validators=[DataRequired()], render_kw={'placeholder': _l('Email addresses or fediverse handles, one per line'), 'autofocus': True})
    submit = SubmitField(_l('Invite'))
