from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, BooleanField, EmailField, TextAreaField, FileField, \
    RadioField, DateField, SelectField, IntegerField, SelectMultipleField, HiddenField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo, Length, Optional
from flask_babel import _, lazy_gettext as _l

from app.utils import MultiCheckboxField


class ProfileForm(FlaskForm):
    title = StringField(_l('Display name'), validators=[Optional(), Length(max=255)])
    email = EmailField(_l('Email address'), validators=[Email(), DataRequired(), Length(min=5, max=255)])
    password_field = PasswordField(_l('Set new password'), validators=[Optional(), Length(min=1, max=50)],
                                   render_kw={"autocomplete": 'new-password'})
    about = TextAreaField(_l('Bio'), validators=[Optional(), Length(min=3, max=5000)], render_kw={'rows': 5})
    extra_label_1 = StringField(_l('Extra field 1 - label'), validators=[Optional(), Length(max=50)], render_kw={"placeholder": _l('Label')})
    extra_text_1 = StringField(_l('Extra field 1 - text'), validators=[Optional(), Length(max=256)], render_kw={"placeholder": _l('Content')})
    extra_label_2 = StringField(_l('Extra field 2 - label'), validators=[Optional(), Length(max=50)], render_kw={"placeholder": _l('Label')})
    extra_text_2 = StringField(_l('Extra field 2 - text'), validators=[Optional(), Length(max=256)], render_kw={"placeholder": _l('Content')})
    extra_label_3 = StringField(_l('Extra field 3 - label'), validators=[Optional(), Length(max=50)], render_kw={"placeholder": _l('Label')})
    extra_text_3 = StringField(_l('Extra field 3 - text'), validators=[Optional(), Length(max=256)], render_kw={"placeholder": _l('Content')})
    extra_label_4 = StringField(_l('Extra field 4 - label'), validators=[Optional(), Length(max=50)], render_kw={"placeholder": _l('Label')})
    extra_text_4 = StringField(_l('Extra field 4 - text'), validators=[Optional(), Length(max=256)], render_kw={"placeholder": _l('Content')})
    matrixuserid = StringField(_l('Matrix User ID'), validators=[Optional(), Length(max=255)],
                               render_kw={'autocomplete': 'off'})
    profile_file = FileField(_l('Avatar image'), render_kw={'accept': 'image/*'})
    banner_file = FileField(_l('Top banner image'), render_kw={'accept': 'image/*'})
    bot = BooleanField(_l('This profile is a bot'))
    timezone = HiddenField(render_kw={'id': 'timezone'})
    submit = SubmitField(_l('Save profile'))

    def validate_email(self, field):
        if current_user.another_account_using_email(field.data):
            raise ValidationError(_l('That email address is already in use by another account'))

    def validate_matrix_user_id(self, matrix_user_id):
        if not matrix_user_id.data.strip().startswith('@'):
            raise ValidationError(_l('Matrix user ids start with @'))


class SettingsForm(FlaskForm):
    interface_language = SelectField(_l('Interface language'), coerce=str, validators=[Optional()],
                                     render_kw={'class': 'form-select'})
    read_languages = MultiCheckboxField(_l('Content language'), coerce=int, validators=[Optional()],
                                        render_kw={'class':'form-multicheck-columns'})
    newsletter = BooleanField(_l('Subscribe to email newsletter'))
    email_unread = BooleanField(_l('Receive email about missed notifications'))
    ignore_bots = BooleanField(_l('Hide posts by bots'))
    nsfw = BooleanField(_l('Show NSFW posts'))
    nsfl = BooleanField(_l('Show NSFL posts'))
    reply_collapse_threshold = IntegerField(_l('Reply collapse threshold'), validators=[Optional()])
    reply_hide_threshold = IntegerField(_l('Reply hide threshold'), validators=[Optional()])
    markdown_editor = BooleanField(_l('Use markdown editor GUI when writing'))
    searchable = BooleanField(_l('Show profile in user list'))
    indexable = BooleanField(_l('My posts appear in search results'))
    hide_read_posts = BooleanField(_l('Do not display posts with which I have already interacted (opened/upvoted/downvoted)'))
    manually_approves_followers = BooleanField(_l('Manually approve followers'))
    vote_privately = BooleanField(_l('Vote privately'))
    feed_auto_follow = BooleanField(_l('Enable Automatic Follow of Feed Communities.'), default=True)
    feed_auto_leave = BooleanField(_l('Enable Automatic Leave of Feed Communities.'), default=False)
    sorts = [('hot', _l('Hot')),
             ('top', _l('Top')),
             ('new', _l('New')),
             ('active', _l('Active')),
             ('scaled', _l('Scaled')),
             ]
    default_sort = SelectField(_l('Default post sort'), choices=sorts, validators=[DataRequired()], coerce=str,
                               render_kw={'class': 'form-select'})
    filters = [('subscribed', _l('Subscribed')),
               ('local', _l('Local')),
               ('popular', _l('Popular')),
               ('all', _l('All')),
               ]
    default_filter = SelectField(_l('Default home filter'), choices=filters, validators=[DataRequired()], coerce=str,
                                 render_kw={'class': 'form-select'})
    theme = SelectField(_l('Theme'), coerce=str, render_kw={'class': 'form-select'})
    compact_levels = [
        ('', _l('No')),
        ('compact-min', _l('Yes')),
        ('compact-min compact-max', _l('YEESSS')),  # this will apply both classes to the body tag
    ]
    compaction = SelectField(_l('Compact UI'), choices=compact_levels, coerce=str, render_kw={'class': 'form-select'})
    fonts = [('', _l('Theme default - fastest')),
             ('atkinson', _l('Atkinson Hyperlegible - low vision')),
             ('inter', _l('Inter - pretty')),
             ('roboto', _l('Roboto - pretty')),
             ]
    font = SelectField(_l('Font'), choices=fonts, validators=[Optional()], coerce=str,
                               render_kw={'class': 'form-select'})
    accept_from = [
        ('0', _l('None')),
        ('1', _l('This instance')),
        ('2', _l('Trusted instances')),
        ('3', _l('All instances')),
    ]
    accept_private_messages = SelectField(_l('Accept private messages from'), choices=accept_from, coerce=int, render_kw={'class': 'form-select'})
    submit = SubmitField(_l('Save settings'))


class ImportExportForm(FlaskForm):
    import_file = FileField(_l('Import community subscriptions and user blocks from Lemmy'))
    export_settings = SubmitField(_l('Export'))
    submit = SubmitField(_l('Import'))


class DeleteAccountForm(FlaskForm):
    submit = SubmitField(_l('Yes, delete my account'))


class ReportUserForm(FlaskForm):
    reason_choices = [('1', _l('Breaks community rules')),
                      ('7', _l('Spam')),
                      ('2', _l('Harassment')),
                      ('3', _l('Threatening violence')),
                      ('4', _l('Promoting hate / genocide')),
                      ('15', _l('Misinformation / disinformation')),
                      ('16', _l('Racism, sexism, transphobia')),
                      ('17', _l('Malicious reporting')),
                      ('6', _l('Sharing personal info - doxing')),
                      ('5', _l('Minor abuse or sexualization')),
                      ('8', _l('Non-consensual intimate media')),
                      ('9', _l('Prohibited transaction')), ('10', _l('Impersonation')),
                      ('11', _l('Copyright violation')), ('12', _l('Trademark violation')),
                      ('13', _l('Self-harm or suicide')),
                      ('14', _l('Other'))]
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


class FilterForm(FlaskForm):
    hide_type_choices = [(0, _l('Show')),
                         (1, _l('Hide completely')),
                         (2, _l('Blur thumbnail')),
                         (3, _l('Make post semi-transparent'))]
    ignore_bots = SelectField(_l('Hide posts by bots'), choices=hide_type_choices,
                              default=0, coerce=int, render_kw={'class': 'form-select'})
    hide_nsfw = SelectField(_l('Show NSFW posts'), choices=hide_type_choices,
                            default=1, coerce=int, render_kw={'class': 'form-select'})
    hide_nsfl = SelectField(_l('Show NSFL posts'), choices=hide_type_choices,
                            default=1, coerce=int, render_kw={'class': 'form-select'})
    reply_collapse_threshold = IntegerField(_l('Reply collapse threshold'))
    reply_hide_threshold = IntegerField(_l('Reply hide threshold'))
    hide_low_quality = BooleanField(_l('Hide posts in low quality communities'))
    submit = SubmitField(_l('Save settings'))


class KeywordFilterEditForm(FlaskForm):
    title = StringField(_l('Name'), validators=[DataRequired(), Length(min=3, max=50)])
    filter_home = BooleanField(_l('Home feed'), default=True)
    filter_posts = BooleanField(_l('Posts in communities'))
    filter_replies = BooleanField(_l('Comments on posts'))
    hide_type_choices = [(0, _l('Make semi-transparent')), (1, _l('Hide completely'))]
    hide_type = RadioField(_l('Action to take'), choices=hide_type_choices, default=1, coerce=int)
    keywords = TextAreaField(_l('Keywords that trigger this filter'),
                             render_kw={'placeholder': 'One keyword or phrase per line', 'rows': 3},
                             validators=[DataRequired(), Length(min=3, max=500)])
    expire_after = DateField(_l('Expire after'), validators=[Optional()])
    submit = SubmitField(_l('Save'))


class RemoteFollowForm(FlaskForm):
    instance_url = StringField(_l('Your remote instance:'), validators=[DataRequired(), Length(min=3, max=50)],
                               render_kw={'placeholder': 'e.g. mastodon.social'})
    type_choices = [
        ('mastodon', _l('Mastodon, Misskey, Akkoma, Iceshrimp and friends')),
        ('friendica', _l('Friendica')),
        ('hubzilla', _l('Hubzilla')),
        ('lemmy', _l('Lemmy')),
        ('pixelfed', _l('Pixelfed')),
    ]

    instance_type = SelectField(_l('Instance type'), choices=type_choices, render_kw={'class': 'form-select'})
    submit = SubmitField(_l('View profile on remote instance'))


class UserNoteForm(FlaskForm):
    note = StringField(_l('User note'), validators=[Optional(), Length(max=50)])
    submit = SubmitField(_l('Save note'))
