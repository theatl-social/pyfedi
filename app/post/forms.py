from flask_wtf import FlaskForm
from wtforms import TextAreaField, SubmitField, BooleanField, StringField, HiddenField
from wtforms.fields.choices import SelectField
from wtforms.validators import DataRequired, Length, ValidationError
from flask_babel import _, lazy_gettext as _l

from app.utils import MultiCheckboxField


class NewReplyForm(FlaskForm):
    body = TextAreaField(_l('Body'), render_kw={'placeholder': 'What are your thoughts?', 'rows': 5}, validators=[DataRequired(), Length(min=1, max=10000)])
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


class MeaCulpaForm(FlaskForm):
    submit = SubmitField(_l('I changed my mind'))


class CrossPostForm(FlaskForm):
    which_community = SelectField(_l('Community to post this link to'), validators=[DataRequired()], coerce=int, render_kw={'class': 'form-select'})
    submit = SubmitField(_l('Next'))


class ConfirmationForm(FlaskForm):
    referrer = HiddenField()
    submit = SubmitField(_l('Yes'), render_kw={'autofocus': True})


class ConfirmationMultiDeleteForm(FlaskForm):
    also_delete_replies = BooleanField(_l('Also delete replies to this comment'))
    submit = SubmitField(_l('Yes'), render_kw={'autofocus': True})
