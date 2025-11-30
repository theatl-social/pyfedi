from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import TextAreaField, SubmitField, BooleanField, StringField, HiddenField
from wtforms.fields.choices import SelectField
from wtforms.validators import DataRequired, Length, ValidationError
from flask_babel import _, lazy_gettext as _l

from app import get_locale
from app.models import utcnow
from app.utils import MultiCheckboxField


class NewReplyForm(FlaskForm):
    body = TextAreaField(_l('Body'), render_kw={'placeholder': 'What are your thoughts?', 'rows': 5, 'class': 'autoresize'},
                         validators=[DataRequired(), Length(min=1, max=10000)])
    notify_author = BooleanField(_l('Notify about replies'))
    distinguished = BooleanField(_l('Distinguish as moderator comment'))
    language_id = SelectField(_l('Language'), validators=[DataRequired()], coerce=int, render_kw={'class': 'form-select'})
    submit = SubmitField(_l('Comment'))


class EditReplyForm(NewReplyForm):
    submit = SubmitField(_l('Save'))


class ReportPostForm(FlaskForm):
    reason_choices = [('1', _l('Breaks community rules')), ('7', _l('Spam')), ('2', _l('Harassment')),
                      ('3', _l('Threatening violence')), ('4', _l('Hate / genocide')),
                      ('15', _l('Misinformation / disinformation')),
                      ('16', _l('Racism, sexism, transphobia')),
                      ('6', _l('Sharing personal info - doxing')),
                      ('5', _l('Minor abuse or sexualization')),
                      ('8', _l('Non-consensual intimate media')),
                      ('9', _l('Prohibited transaction')), ('10', _l('Impersonation')),
                      ('11', _l('Copyright violation')), ('12', _l('Trademark violation')),
                      ('13', _l('Self-harm or suicide')),
                      ('14', _l('Other'))]
    reasons = MultiCheckboxField(_l('Reason'), choices=reason_choices)
    description = StringField(_l('More info'), validators=[Length(max=256)])
    report_remote = BooleanField('Also send report to originating instance')
    submit = SubmitField(_l('Report'))

    def reasons_to_string(self, reason_data) -> str:
        result = []
        for reason_id in reason_data:
            for choice in self.reason_choices:
                if choice[0] == reason_id:
                    result.append(str(choice[1]))
        return ', '.join(result)[:255]


class MeaCulpaForm(FlaskForm):
    submit = SubmitField(_l('I changed my mind'))


class CrossPostForm(FlaskForm):
    which_community = SelectField(_l('Community to post this link to'), validators=[DataRequired()], coerce=int, render_kw={'class': 'form-select'})
    submit = SubmitField(_l('Next'))


class ConfirmationForm(FlaskForm):
    referrer = HiddenField()
    submit = SubmitField(_l('Yes'), render_kw={'autofocus': True})


class DeleteConfirmationForm(FlaskForm):
    referrer = HiddenField()
    reason = StringField(_l('Reason'), validators=[Length(max=512)])
    submit = SubmitField(_l('Yes'), render_kw={'autofocus': True})


class ConfirmationMultiDeleteForm(FlaskForm):
    reason = StringField(_l('Reason'), validators=[Length(max=512)])
    also_delete_replies = BooleanField(_l('Also delete replies to this comment'))
    submit = SubmitField(_l('Yes'), render_kw={'autofocus': True})


class FlairPostForm(FlaskForm):
    referrer = HiddenField()
    flair = MultiCheckboxField(_l('Flair'), coerce=int, render_kw={'class': 'form-multicheck-columns'})
    nsfw = BooleanField(_l('NSFW'))
    nsfl = BooleanField(_l('Gore/gross'))
    ai_generated = BooleanField(_l('AI generated'))
    submit = SubmitField(_l('Save'))


class NewReminderForm(FlaskForm):
    remind_at = StringField(_l('When would you like to be reminded?'), validators=[DataRequired(), Length(max=512)],
                            render_kw={'placeholder': _l("e.g. 'in 2 weeks'")})
    referrer = HiddenField()
    submit = SubmitField(_l('Save'))

    def validate_remind_at(self, remind_at):
        import dateparser
        import arrow
        try:
            x = dateparser.parse(remind_at.data, settings={'RELATIVE_BASE': datetime.now(),
                                                           "RETURN_AS_TIMEZONE_AWARE": True,
                                                           }, languages=[get_locale()])

            if x is None or arrow.get(x).to('UTC').datetime < utcnow(naive=False):
                raise ValidationError(_l('Invalid.'))
        except Exception:
            raise ValidationError(_l('Invalid.'))


class ShareMastodonForm(FlaskForm):
    domain = StringField(_l('Mastodon instance domain name'), validators=[Length(max=512)])
    submit = SubmitField(_l('Share'))
